//go:build linux

package executor

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
)

// coletor guarda as linhas recebidas; o executor chama de uma goroutine.
type coletor struct {
	mu     sync.Mutex
	linhas []string
}

func (c *coletor) acrescentar(l string) {
	c.mu.Lock()
	c.linhas = append(c.linhas, l)
	c.mu.Unlock()
}

func (c *coletor) todas() []string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]string(nil), c.linhas...)
}

// rodarSh roda um trecho de shell. Só nos testes: o agente nunca usa
// shell para rodar robôs.
func rodarSh(t *testing.T, trecho string, ajustar func(*Pedido)) (Resultado, *coletor) {
	t.Helper()
	c := &coletor{}
	p := Pedido{
		Programa:           "/bin/sh",
		Args:               []string{"-c", trecho},
		Pasta:              t.TempDir(),
		Timeout:            10 * time.Second,
		AoReceberLinha:     c.acrescentar,
		EsperaEncerramento: 300 * time.Millisecond,
	}
	if ajustar != nil {
		ajustar(&p)
	}
	r, err := Executar(p)
	if err != nil {
		t.Fatalf("Executar: %v", err)
	}
	return r, c
}

func TestConcluidoJuntaSaidaPadraoEErroNaOrdem(t *testing.T) {
	r, c := rodarSh(t, `echo um; echo dois >&2; printf 'tres\r\n'; printf 'sem quebra'`, nil)

	if r.Motivo != protocolo.Concluido || r.CodigoSaida != 0 {
		t.Fatalf("resultado = %+v", r)
	}
	esperado := []string{"um", "dois", "tres", "sem quebra"}
	if got := c.todas(); strings.Join(got, "|") != strings.Join(esperado, "|") {
		t.Errorf("linhas = %q, esperado %q", got, esperado)
	}
}

func TestCodigoDeSaidaDiferenteDeZero(t *testing.T) {
	r, _ := rodarSh(t, "exit 3", nil)
	if r.Motivo != protocolo.Concluido || r.CodigoSaida != 3 {
		t.Fatalf("resultado = %+v", r)
	}
}

func TestUsaAPastaDeTrabalho(t *testing.T) {
	pasta := t.TempDir()
	_, c := rodarSh(t, "pwd", func(p *Pedido) { p.Pasta = pasta })
	real, _ := filepath.EvalSymlinks(pasta)
	if got := c.todas(); len(got) != 1 || got[0] != real {
		t.Errorf("pwd = %q, esperado %q", got, real)
	}
}

func TestTempoEsgotadoEncerraOProcesso(t *testing.T) {
	inicio := time.Now()
	r, _ := rodarSh(t, "sleep 30", func(p *Pedido) { p.Timeout = 300 * time.Millisecond })

	if r.Motivo != protocolo.TempoEsgotado {
		t.Fatalf("motivo = %q", r.Motivo)
	}
	if r.CodigoSaida != -int(syscall.SIGTERM) {
		t.Errorf("codigo = %d, esperado %d", r.CodigoSaida, -int(syscall.SIGTERM))
	}
	if d := time.Since(inicio); d > 5*time.Second {
		t.Errorf("demorou %v", d)
	}
}

func TestPararEncerraOProcesso(t *testing.T) {
	parar := make(chan struct{})
	time.AfterFunc(200*time.Millisecond, func() { close(parar) })

	r, c := rodarSh(t, "echo antes; sleep 30; echo depois", func(p *Pedido) { p.Parar = parar })

	if r.Motivo != protocolo.Parado {
		t.Fatalf("motivo = %q", r.Motivo)
	}
	if got := c.todas(); len(got) != 1 || got[0] != "antes" {
		t.Errorf("linhas = %q", got)
	}
}

func TestQuemIgnoraSigtermEEncerradoAForca(t *testing.T) {
	parar := make(chan struct{})
	time.AfterFunc(200*time.Millisecond, func() { close(parar) })

	r, _ := rodarSh(t, `trap '' TERM; echo pronto; while :; do sleep 0.1; done`,
		func(p *Pedido) { p.Parar = parar })

	if r.Motivo != protocolo.Parado || r.CodigoSaida != -int(syscall.SIGKILL) {
		t.Fatalf("resultado = %+v", r)
	}
}

func TestFilhosSaoEncerradosJunto(t *testing.T) {
	arquivoPid := filepath.Join(t.TempDir(), "filho.pid")
	parar := make(chan struct{})
	time.AfterFunc(300*time.Millisecond, func() { close(parar) })

	// O filho em segundo plano faz o papel do navegador aberto pelo robô.
	rodarSh(t, "sleep 60 & echo $! > "+arquivoPid+"; wait",
		func(p *Pedido) { p.Parar = parar })

	conteudo, err := os.ReadFile(arquivoPid)
	if err != nil {
		t.Fatal(err)
	}
	pid, _ := strconv.Atoi(strings.TrimSpace(string(conteudo)))
	if pid <= 0 {
		t.Fatalf("pid inválido: %q", conteudo)
	}
	if continuaVivo(pid) {
		_ = syscall.Kill(pid, syscall.SIGKILL)
		t.Errorf("o filho %d continuou vivo", pid)
	}
}

func TestFilhoQueSobraDepoisDoFimEEncerrado(t *testing.T) {
	arquivoPid := filepath.Join(t.TempDir(), "filho.pid")

	// O robô termina sozinho, mas deixa um filho com a saída aberta.
	r, _ := rodarSh(t, "sleep 60 & echo $! > "+arquivoPid+"; echo fim", nil)

	if r.Motivo != protocolo.Concluido || r.CodigoSaida != 0 {
		t.Fatalf("resultado = %+v", r)
	}
	conteudo, _ := os.ReadFile(arquivoPid)
	pid, _ := strconv.Atoi(strings.TrimSpace(string(conteudo)))
	if pid > 0 && continuaVivo(pid) {
		_ = syscall.Kill(pid, syscall.SIGKILL)
		t.Errorf("o filho %d continuou vivo", pid)
	}
}

func TestLinhaLongaChegaInteira(t *testing.T) {
	_, c := rodarSh(t, `head -c 200000 /dev/zero | tr '\0' a; echo`, nil)
	if got := c.todas(); len(got) != 1 || len(got[0]) != 200000 {
		t.Fatalf("recebeu %d linhas", len(got))
	}
}

func TestProgramaInexistenteDevolveErro(t *testing.T) {
	_, err := Executar(Pedido{
		Programa:       "/nao/existe/programa",
		Pasta:          t.TempDir(),
		AoReceberLinha: func(string) {},
	})
	if err == nil {
		t.Fatal("esperava erro ao iniciar programa inexistente")
	}
}

// continuaVivo diz se o processo segue rodando depois de até 2 s. Um
// processo morto ainda não recolhido (zumbi) conta como encerrado.
func continuaVivo(pid int) bool {
	prazo := time.Now().Add(2 * time.Second)
	for time.Now().Before(prazo) {
		estado, err := os.ReadFile("/proc/" + strconv.Itoa(pid) + "/stat")
		if err != nil {
			return false
		}
		// O campo de estado vem logo depois do ")" do nome.
		campos := strings.Fields(string(estado[strings.LastIndexByte(string(estado), ')')+1:]))
		if len(campos) > 0 && campos[0] == "Z" {
			return false
		}
		time.Sleep(50 * time.Millisecond)
	}
	return true
}

func TestRodaComOutroUsuario(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("trocar de usuário exige root")
	}
	var linhas []string
	resultado, err := Executar(Pedido{
		Programa:       "id",
		Args:           []string{"-u"},
		Pasta:          os.TempDir(),
		Usuario:        &Usuario{UID: 65534, GID: 65534},
		AoReceberLinha: func(l string) { linhas = append(linhas, l) },
	})
	if err != nil || resultado.CodigoSaida != 0 {
		t.Fatalf("resultado = %+v, err = %v", resultado, err)
	}
	if len(linhas) != 1 || linhas[0] != "65534" {
		t.Errorf("rodou como %q, esperado 65534", linhas)
	}
}
