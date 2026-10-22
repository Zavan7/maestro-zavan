// Package execucoes atende os comandos "iniciar" e "parar": roda cada
// robô na sua goroutine, junta o log em lotes e informa como terminou.
//
// O gerente não conhece a conexão. Ele só chama a função Enviar, que
// coloca a mensagem na fila de saída; se a conexão cair no meio de uma
// execução, o robô continua rodando e as mensagens esperam a reconexão.
package execucoes

import (
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/ambiente"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/executor"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/robo"
)

// IntervaloLote é de quanto em quanto tempo as linhas acumuladas saem.
const IntervaloLote = 500 * time.Millisecond

// TempoMaximoPreparo é o limite de cada comando de preparo (uv sync,
// poetry install...). O tempo limite do robô conta só a execução dele:
// a primeira instalação pode demorar bem mais que o robô.
const TempoMaximoPreparo = 15 * time.Minute

// Opcoes reúne a configuração do gerente.
type Opcoes struct {
	// PastaRobos é a pasta aprovada: só scripts dentro dela rodam.
	PastaRobos string
	// Programas são os executáveis de cada gerenciador de dependências.
	Programas ambiente.Programas
	// PastaVenvs, se definida, recebe um ambiente por robô, no lugar do
	// .venv dentro da pasta do robô.
	PastaVenvs string
	// TempoPreparo substitui TempoMaximoPreparo se positivo.
	TempoPreparo time.Duration
	// Enviar entrega uma mensagem do protocolo à fila de saída.
	Enviar func(any)
	Logger *slog.Logger
	// IntervaloLote e EsperaEncerramento substituem os padrões quando
	// positivos (os testes usam valores menores).
	IntervaloLote      time.Duration
	EsperaEncerramento time.Duration
}

// Gerente acompanha as execuções em andamento.
type Gerente struct {
	op     Opcoes
	mu     sync.Mutex
	ativas map[int64]*ativa
	grupo  sync.WaitGroup
}

// ativa é uma execução em andamento e o canal que a manda parar.
type ativa struct {
	parar  chan struct{}
	parada sync.Once
}

func (a *ativa) pedirParada() { a.parada.Do(func() { close(a.parar) }) }

// Novo cria um Gerente.
func Novo(op Opcoes) *Gerente {
	if op.IntervaloLote <= 0 {
		op.IntervaloLote = IntervaloLote
	}
	if op.TempoPreparo <= 0 {
		op.TempoPreparo = TempoMaximoPreparo
	}
	if op.Logger == nil {
		op.Logger = slog.Default()
	}
	return &Gerente{op: op, ativas: make(map[int64]*ativa)}
}

// Atender trata um comando do Maestro.
func (g *Gerente) Atender(msg protocolo.Recebida) {
	switch msg.Tipo {
	case "iniciar":
		g.iniciar(msg)
	case "parar":
		g.parar(msg.ExecucaoID)
	case "erro":
		// O Maestro só manda "erro" quando o agente fere o protocolo:
		// é bug do agente, então vai para o log como erro.
		g.op.Logger.Error("o Maestro apontou erro de protocolo", "mensagem", msg.Mensagem)
	default:
		g.op.Logger.Warn("mensagem de tipo desconhecido ignorada", "tipo", msg.Tipo)
	}
}

// Encerrar para todas as execuções e espera os processos saírem. Usado
// quando o agente desliga, para não deixar robô órfão na máquina.
func (g *Gerente) Encerrar() {
	g.mu.Lock()
	for _, a := range g.ativas {
		a.pedirParada()
	}
	g.mu.Unlock()
	g.grupo.Wait()
}

// iniciar registra a execução e a roda numa goroutine própria.
func (g *Gerente) iniciar(msg protocolo.Recebida) {
	if msg.ExecucaoID <= 0 {
		g.op.Logger.Warn("iniciar sem execucao_id válido ignorado", "execucao_id", msg.ExecucaoID)
		return
	}
	g.mu.Lock()
	if _, existe := g.ativas[msg.ExecucaoID]; existe {
		g.mu.Unlock()
		g.op.Logger.Warn("iniciar repetido ignorado", "execucao_id", msg.ExecucaoID)
		return
	}
	a := &ativa{parar: make(chan struct{})}
	g.ativas[msg.ExecucaoID] = a
	g.grupo.Add(1)
	g.mu.Unlock()

	// O "iniciado" sai antes de a goroutine começar: o Maestro pode
	// responder "parar" a ele, e a execução já está registrada.
	g.op.Enviar(protocolo.NovoIniciado(msg.ExecucaoID))
	g.op.Logger.Info("execução iniciada", "execucao_id", msg.ExecucaoID, "robo", msg.Robo)
	go func() {
		defer g.grupo.Done()
		defer g.remover(msg.ExecucaoID)
		g.executar(msg, a.parar)
	}()
}

// parar pede a parada de uma execução em andamento. Execução que não
// existe (ainda não começou ou já terminou) é ignorada.
func (g *Gerente) parar(execucaoID int64) {
	g.mu.Lock()
	a, existe := g.ativas[execucaoID]
	g.mu.Unlock()
	if !existe {
		g.op.Logger.Info("parar de execução desconhecida ignorado", "execucao_id", execucaoID)
		return
	}
	g.op.Logger.Info("parada pedida", "execucao_id", execucaoID)
	a.pedirParada()
}

func (g *Gerente) remover(execucaoID int64) {
	g.mu.Lock()
	delete(g.ativas, execucaoID)
	g.mu.Unlock()
}

// executar resolve o robô, roda e manda o log em lotes e o "fim".
func (g *Gerente) executar(msg protocolo.Recebida, parar <-chan struct{}) {
	id := msg.ExecucaoID
	lote := novoLote()

	recusar := func(motivo string) {
		g.op.Logger.Warn("execução recusada", "execucao_id", id, "motivo", motivo)
		g.enviarLote(id, []string{motivo})
		g.op.Enviar(protocolo.NovoFim(id, protocolo.ScriptInvalido, nil))
	}

	script, err := robo.Resolver(g.op.PastaRobos, msg.Robo)
	if err != nil {
		recusar(err.Error())
		return
	}
	select {
	case <-parar:
		// Cancelada no caminho: o Maestro respondeu "parar" ao
		// "iniciado". Não roda o robô.
		g.op.Enviar(protocolo.NovoFim(id, protocolo.Parado, nil))
		return
	default:
	}

	// Despacha o que foi acumulado a cada intervalo, mesmo com o robô
	// calado; nada sai quando não há linha nova.
	pararDespacho := make(chan struct{})
	despachoTerminou := make(chan struct{})
	go func() {
		defer close(despachoTerminou)
		relogio := time.NewTicker(g.op.IntervaloLote)
		defer relogio.Stop()
		for {
			select {
			case <-pararDespacho:
				return
			case <-relogio.C:
				g.enviarLote(id, lote.tirar())
			}
		}
	}()

	motivo, codigo := g.rodarNoAmbiente(script, ambiente.Plano.Comando,
		time.Duration(msg.TimeoutSegundos)*time.Second, parar, lote.acrescentar)
	close(pararDespacho)
	<-despachoTerminou
	// O último lote sai antes do "fim", como o protocolo pede.
	g.enviarLote(id, lote.tirar())

	g.op.Enviar(protocolo.NovoFim(id, motivo, codigo))
	g.op.Logger.Info("execução terminada", "execucao_id", id, "motivo", motivo)
}

// RodarNoAmbiente prepara o ambiente de uma pasta de robô e roda o
// Python dele com args, sem tempo limite. É o subcomando "agente
// ambiente", usado para instalar os navegadores do Playwright no ambiente
// de cada robô: "-m playwright install firefox".
func (g *Gerente) RodarNoAmbiente(
	pastaDoRobo string, args []string, linha func(string),
) (protocolo.Motivo, *int) {
	// O nome do arquivo não importa: o plano só olha a pasta dele.
	referencia := filepath.Join(pastaDoRobo, "main.py")
	montar := func(p ambiente.Plano, _ string) []string {
		return append(append([]string{}, p.Python...), args...)
	}
	return g.rodarNoAmbiente(referencia, montar, 0, nil, linha)
}

// rodarNoAmbiente detecta o gerenciador de dependências do robô,
// prepara as dependências e roda o comando que montar devolve dentro do
// ambiente dele. Tudo vai para o log: o que foi detectado, cada comando
// de preparo e a saída dele, e então a saída do robô. Devolve o motivo
// do fim e o código de saída, nil quando nada chegou a rodar.
func (g *Gerente) rodarNoAmbiente(
	script string, montar func(ambiente.Plano, string) []string,
	timeout time.Duration, parar <-chan struct{}, linha func(string),
) (protocolo.Motivo, *int) {
	plano := ambiente.Planejar(script, g.op.Programas, g.op.PastaRobos, g.op.PastaVenvs)
	env := append(ambiente.AmbienteLimpo(os.Environ()), plano.Env...)
	linha(plano.Descricao())
	if plano.Programa != "" {
		if _, err := exec.LookPath(plano.Programa); err != nil {
			linha(fmt.Sprintf("%s o robô usa %s, mas %q não está instalado nesta máquina",
				ambiente.Prefixo, plano.Ferramenta, plano.Programa))
			return protocolo.AmbienteInvalido, nil
		}
	}

	rodar := func(comando []string, timeout time.Duration) (executor.Resultado, error) {
		return executor.Executar(executor.Pedido{
			Programa:           comando[0],
			Args:               comando[1:],
			Pasta:              plano.Pasta,
			Env:                env,
			Timeout:            timeout,
			Parar:              parar,
			AoReceberLinha:     linha,
			EsperaEncerramento: g.op.EsperaEncerramento,
		})
	}

	for _, passo := range plano.Preparo {
		linha(ambiente.Prefixo + " $ " + strings.Join(passo, " "))
		resultado, err := rodar(passo, g.op.TempoPreparo)
		codigo := resultado.CodigoSaida
		switch {
		case err != nil:
			linha(fmt.Sprintf("%s o ambiente do robô não abriu: %v", ambiente.Prefixo, err))
			return protocolo.AmbienteInvalido, nil
		case resultado.Motivo == protocolo.Parado:
			return protocolo.Parado, &codigo
		case resultado.Motivo == protocolo.TempoEsgotado:
			linha(fmt.Sprintf("%s preparo excedeu o limite de %.0fs",
				ambiente.Prefixo, g.op.TempoPreparo.Seconds()))
			return protocolo.PreparoFalhou, &codigo
		case codigo != 0:
			linha(fmt.Sprintf("%s preparo falhou (código %d)", ambiente.Prefixo, codigo))
			return protocolo.PreparoFalhou, &codigo
		}
	}

	resultado, err := rodar(montar(plano, script), timeout)
	if err != nil {
		linha(fmt.Sprintf("%s o ambiente do robô não abriu: %v", ambiente.Prefixo, err))
		return protocolo.AmbienteInvalido, nil
	}
	codigo := resultado.CodigoSaida
	return resultado.Motivo, &codigo
}

// enviarLote manda as linhas em mensagens "log" dentro dos limites do
// protocolo. Lista vazia não gera mensagem.
func (g *Gerente) enviarLote(id int64, linhas []string) {
	for _, parte := range Dividir(linhas) {
		g.op.Enviar(protocolo.NovoLog(id, parte))
	}
}

// Dividir corta as linhas nos limites do protocolo: cada linha com até
// MaxCaracteresPorLinha caracteres (as mais longas viram várias) e cada
// mensagem com até MaxLinhasPorMensagem linhas.
func Dividir(linhas []string) [][]string {
	var cortadas []string
	for _, linha := range linhas {
		runas := []rune(linha)
		if len(runas) <= protocolo.MaxCaracteresPorLinha {
			cortadas = append(cortadas, linha)
			continue
		}
		for len(runas) > 0 {
			n := min(len(runas), protocolo.MaxCaracteresPorLinha)
			cortadas = append(cortadas, string(runas[:n]))
			runas = runas[n:]
		}
	}
	var partes [][]string
	for len(cortadas) > 0 {
		n := min(len(cortadas), protocolo.MaxLinhasPorMensagem)
		partes = append(partes, cortadas[:n])
		cortadas = cortadas[n:]
	}
	return partes
}

// lote acumula linhas entre um despacho e outro.
type lote struct {
	mu     sync.Mutex
	linhas []string
}

func novoLote() *lote { return &lote{} }

func (l *lote) acrescentar(linha string) {
	l.mu.Lock()
	l.linhas = append(l.linhas, linha)
	l.mu.Unlock()
}

func (l *lote) tirar() []string {
	l.mu.Lock()
	defer l.mu.Unlock()
	linhas := l.linhas
	l.linhas = nil
	return linhas
}
