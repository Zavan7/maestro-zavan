// Package executor roda o processo de um robô, entrega a saída linha a
// linha e o encerra quando o tempo acaba ou o Maestro pede para parar.
//
// É a versão em Go de robots/executor.py e segue o mesmo contrato:
// saída padrão e de erro juntas, na ordem em que o robô escreveu; grupo
// de processos próprio, para o encerramento alcançar os filhos
// (navegador, chromedriver); SIGTERM primeiro e SIGKILL depois da espera.
package executor

import (
	"bufio"
	"errors"
	"io"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
)

// EsperaEncerramentoPadrao é a tolerância entre o SIGTERM e o SIGKILL.
const EsperaEncerramentoPadrao = 5 * time.Second

// Pedido descreve uma execução.
type Pedido struct {
	Programa string
	Args     []string
	Pasta    string
	// Env é o ambiente do processo; nil herda o do agente.
	Env []string
	// Timeout é o tempo máximo; zero ou negativo é sem limite.
	Timeout time.Duration
	// Parar, quando fechado, encerra o processo com motivo "parado".
	Parar <-chan struct{}
	// AoReceberLinha recebe cada linha da saída, sem a quebra de linha.
	AoReceberLinha func(string)
	// EsperaEncerramento substitui EsperaEncerramentoPadrao se positiva.
	EsperaEncerramento time.Duration
	// Usuario, se definido, é o usuário do sistema com que o processo
	// roda. Exige que o agente possa trocar de usuário (root).
	Usuario *Usuario
}

// Usuario é um usuário e um grupo do sistema, pelos números.
type Usuario struct {
	UID, GID uint32
}

// Resultado diz por que a execução terminou e com qual código de saída.
// Processo encerrado por sinal devolve o sinal negativo (-15, -9), como
// o subprocess do Python.
type Resultado struct {
	Motivo      protocolo.Motivo
	CodigoSaida int
}

// Executar roda o pedido até o processo terminar, o tempo acabar ou
// Parar ser fechado. O programa é chamado com a lista de argumentos,
// nunca por um shell. Devolve erro só quando o processo nem inicia.
func Executar(p Pedido) (Resultado, error) {
	espera := p.EsperaEncerramento
	if espera <= 0 {
		espera = EsperaEncerramentoPadrao
	}

	leitura, escrita, err := os.Pipe()
	if err != nil {
		return Resultado{}, err
	}
	cmd := exec.Command(p.Programa, p.Args...)
	cmd.Dir = p.Pasta
	cmd.Env = p.Env
	cmd.Stdout = escrita
	cmd.Stderr = escrita
	prepararProcesso(cmd, p.Usuario)
	if err := cmd.Start(); err != nil {
		_ = leitura.Close()
		_ = escrita.Close()
		return Resultado{}, err
	}
	// O agente fecha a ponta dele; a saída só termina quando o robô e
	// todos os filhos fecharem as deles.
	_ = escrita.Close()

	linhas := make(chan string, 256)
	go lerLinhas(leitura, linhas)

	terminou := make(chan struct{})
	go func() {
		_ = cmd.Wait()
		close(terminou)
	}()

	var limite <-chan time.Time
	if p.Timeout > 0 {
		relogio := time.NewTimer(p.Timeout)
		defer relogio.Stop()
		limite = relogio.C
	}
	parar := p.Parar
	motivo := protocolo.Concluido
	var forcar, prazoLeitura <-chan time.Time

	encerrar := func(m protocolo.Motivo) {
		motivo = m
		limite, parar = nil, nil
		sinalizarGrupo(cmd, sinalEducado)
		forcar = time.After(espera)
	}

	entrada := linhas
laco:
	for {
		select {
		case linha, aberta := <-entrada:
			if !aberta {
				entrada = nil
				if terminou == nil {
					break laco
				}
				continue
			}
			p.AoReceberLinha(linha)
		case <-terminou:
			terminou = nil
			// Terminou sozinho: tempo e parada não valem mais.
			limite, parar = nil, nil
			if entrada == nil {
				break laco
			}
			// Um filho pode ter ficado com a saída aberta; espera um
			// pouco pelas últimas linhas e segue.
			prazoLeitura = time.After(espera)
		case <-prazoLeitura:
			break laco
		case <-limite:
			encerrar(protocolo.TempoEsgotado)
		case <-parar:
			encerrar(protocolo.Parado)
		case <-forcar:
			forcar = nil
			sinalizarGrupo(cmd, sinalForcado)
		}
	}

	// Filhos que sobraram depois de o robô terminar (um navegador que
	// não foi fechado, por exemplo) são encerrados junto.
	sinalizarGrupo(cmd, sinalForcado)
	if terminou != nil {
		<-terminou
	}
	if entrada != nil {
		drenar(entrada, p.AoReceberLinha, time.Second)
	}
	return Resultado{Motivo: motivo, CodigoSaida: codigoSaida(cmd.ProcessState)}, nil
}

// lerLinhas lê a saída e entrega cada linha no canal, que é fechado
// quando a saída termina. bufio.Reader, e não Scanner, para aceitar
// linhas de qualquer tamanho.
func lerLinhas(saida io.ReadCloser, linhas chan<- string) {
	defer close(linhas)
	defer saida.Close()
	leitor := bufio.NewReader(saida)
	for {
		linha, err := leitor.ReadString('\n')
		if linha != "" {
			linha = strings.TrimRight(linha, "\r\n")
			linhas <- strings.ToValidUTF8(linha, "�")
		}
		if err != nil {
			if !errors.Is(err, io.EOF) && !errors.Is(err, os.ErrClosed) {
				linhas <- "[agente] erro ao ler a saída: " + err.Error()
			}
			return
		}
	}
}

// drenar entrega o que ainda estiver no canal, por no máximo prazo.
func drenar(linhas <-chan string, entregar func(string), prazo time.Duration) {
	fim := time.After(prazo)
	for {
		select {
		case linha, aberta := <-linhas:
			if !aberta {
				return
			}
			entregar(linha)
		case <-fim:
			return
		}
	}
}
