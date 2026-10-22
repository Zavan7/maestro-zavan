//go:build unix

package execucoes

import (
	"io"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/ambiente"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
)

// caixa guarda as mensagens que o gerente mandaria ao Maestro.
type caixa struct {
	mu        sync.Mutex
	mensagens []any
	chegou    chan struct{}
}

func novaCaixa() *caixa { return &caixa{chegou: make(chan struct{}, 1000)} }

func (c *caixa) enviar(v any) {
	c.mu.Lock()
	c.mensagens = append(c.mensagens, v)
	c.mu.Unlock()
	c.chegou <- struct{}{}
}

func (c *caixa) todas() []any {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]any(nil), c.mensagens...)
}

// esperarFim espera a mensagem "fim" da execução e a devolve.
func (c *caixa) esperarFim(t *testing.T, id int64) protocolo.Fim {
	t.Helper()
	prazo := time.After(15 * time.Second)
	for {
		for _, m := range c.todas() {
			if fim, ok := m.(protocolo.Fim); ok && fim.ExecucaoID == id {
				return fim
			}
		}
		select {
		case <-c.chegou:
		case <-prazo:
			t.Fatalf("o fim da execução %d não chegou; mensagens: %+v", id, c.todas())
		}
	}
}

// linhasComAmbiente junta as linhas de todas as mensagens "log" da
// execução, inclusive as que o agente escreve sobre o ambiente.
func (c *caixa) linhasComAmbiente(id int64) []string {
	var todas []string
	for _, m := range c.todas() {
		if log, ok := m.(protocolo.Log); ok && log.ExecucaoID == id {
			todas = append(todas, log.Linhas...)
		}
	}
	return todas
}

// linhas devolve só a saída do robô, sem as linhas "[ambiente]".
func (c *caixa) linhas(id int64) []string {
	var saida []string
	for _, linha := range c.linhasComAmbiente(id) {
		if !strings.HasPrefix(linha, ambiente.Prefixo) {
			saida = append(saida, linha)
		}
	}
	return saida
}

// preparar cria a pasta aprovada com um robô e um Gerente ligado à caixa.
func preparar(t *testing.T, robos map[string]string) (*Gerente, *caixa) {
	t.Helper()
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 não encontrado")
	}
	pasta := t.TempDir()
	for nome, codigo := range robos {
		caminho := filepath.Join(pasta, nome)
		if err := os.MkdirAll(filepath.Dir(caminho), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(caminho, []byte(codigo), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	c := novaCaixa()
	g := Novo(Opcoes{
		PastaRobos:         pasta,
		Programas:          ambiente.Programas{UV: "uv", Poetry: "poetry", PDM: "pdm", Pipenv: "pipenv", Python: python},
		Enviar:             c.enviar,
		Logger:             slog.New(slog.NewTextHandler(io.Discard, nil)),
		IntervaloLote:      50 * time.Millisecond,
		EsperaEncerramento: 300 * time.Millisecond,
	})
	t.Cleanup(g.Encerrar)
	return g, c
}

func iniciar(id int64, robo string, timeout int) protocolo.Recebida {
	return protocolo.Recebida{Tipo: "iniciar", ExecucaoID: id, Robo: robo, TimeoutSegundos: timeout}
}

func TestIniciarMandaIniciadoLogEFimNaOrdem(t *testing.T) {
	g, c := preparar(t, map[string]string{
		"coleta/main.py": "import sys\nprint('etapa 1')\nprint('aviso', file=sys.stderr)\nprint('etapa 2')\n",
	})

	g.Atender(iniciar(7, "coleta/main.py", 30))
	fim := c.esperarFim(t, 7)

	if fim.Motivo != protocolo.Concluido || fim.CodigoSaida == nil || *fim.CodigoSaida != 0 {
		t.Fatalf("fim = %+v", fim)
	}
	if got := c.linhas(7); !slices.Equal(got, []string{"etapa 1", "aviso", "etapa 2"}) {
		t.Errorf("linhas = %q", got)
	}
	todas := c.todas()
	if _, ok := todas[0].(protocolo.Iniciado); !ok {
		t.Errorf("primeira mensagem = %+v, esperado iniciado", todas[0])
	}
	if _, ok := todas[len(todas)-1].(protocolo.Fim); !ok {
		t.Errorf("última mensagem = %+v, esperado fim", todas[len(todas)-1])
	}
}

func TestFalhaDevolveOCodigoDeSaida(t *testing.T) {
	g, c := preparar(t, map[string]string{"falha.py": "raise SystemExit(4)\n"})

	g.Atender(iniciar(8, "falha.py", 30))
	fim := c.esperarFim(t, 8)

	if fim.Motivo != protocolo.Concluido || fim.CodigoSaida == nil || *fim.CodigoSaida != 4 {
		t.Fatalf("fim = %+v", fim)
	}
}

func TestRoboForaDaPastaEScriptInvalido(t *testing.T) {
	g, c := preparar(t, nil)

	for id, robo := range map[int64]string{10: "../fora.py", 11: "nao_existe.py", 12: "/etc/passwd"} {
		g.Atender(iniciar(id, robo, 30))
		fim := c.esperarFim(t, id)
		if fim.Motivo != protocolo.ScriptInvalido || fim.CodigoSaida != nil {
			t.Errorf("%q: fim = %+v", robo, fim)
		}
		if len(c.linhas(id)) != 1 {
			t.Errorf("%q: esperava uma linha com o motivo, veio %q", robo, c.linhas(id))
		}
	}
}

func TestPararEncerraAExecucao(t *testing.T) {
	g, c := preparar(t, map[string]string{
		"lento.py": "import time\nprint('comecei')\ntime.sleep(30)\n",
	})

	g.Atender(iniciar(20, "lento.py", 60))
	// Espera o robô falar antes de pedir a parada.
	prazo := time.Now().Add(10 * time.Second)
	for len(c.linhas(20)) == 0 && time.Now().Before(prazo) {
		time.Sleep(20 * time.Millisecond)
	}
	g.Atender(protocolo.Recebida{Tipo: "parar", ExecucaoID: 20})
	fim := c.esperarFim(t, 20)

	if fim.Motivo != protocolo.Parado {
		t.Fatalf("fim = %+v", fim)
	}
	if got := c.linhas(20); !slices.Equal(got, []string{"comecei"}) {
		t.Errorf("linhas = %q", got)
	}
}

func TestTempoEsgotado(t *testing.T) {
	g, c := preparar(t, map[string]string{"lento.py": "import time\ntime.sleep(30)\n"})

	g.Atender(iniciar(30, "lento.py", 1))
	fim := c.esperarFim(t, 30)

	if fim.Motivo != protocolo.TempoEsgotado {
		t.Fatalf("fim = %+v", fim)
	}
}

func TestPararDesconhecidoEIniciarRepetidoSaoIgnorados(t *testing.T) {
	g, c := preparar(t, map[string]string{"lento.py": "import time\ntime.sleep(1)\n"})

	g.Atender(protocolo.Recebida{Tipo: "parar", ExecucaoID: 99})
	g.Atender(iniciar(40, "lento.py", 30))
	g.Atender(iniciar(40, "lento.py", 30))
	c.esperarFim(t, 40)

	iniciados := 0
	for _, m := range c.todas() {
		if _, ok := m.(protocolo.Iniciado); ok {
			iniciados++
		}
	}
	if iniciados != 1 {
		t.Errorf("iniciados = %d, esperado 1", iniciados)
	}
}

func TestRoboNaoEnxergaOToken(t *testing.T) {
	t.Setenv("MAESTRO_TOKEN", "mae_segredo")
	g, c := preparar(t, map[string]string{
		"espiao.py": "import os\nprint(os.environ.get('MAESTRO_TOKEN', 'sem token'))\nprint(os.environ.get('PYTHONUNBUFFERED'))\n",
	})

	g.Atender(iniciar(50, "espiao.py", 30))
	c.esperarFim(t, 50)

	if got := c.linhas(50); !slices.Equal(got, []string{"sem token", "1"}) {
		t.Errorf("linhas = %q", got)
	}
}

func TestDividirRespeitaOsLimites(t *testing.T) {
	longa := strings.Repeat("é", protocolo.MaxCaracteresPorLinha*2+5)
	linhas := []string{longa}
	for range protocolo.MaxLinhasPorMensagem + 10 {
		linhas = append(linhas, "x")
	}

	partes := Dividir(linhas)

	total := 0
	for _, parte := range partes {
		if len(parte) > protocolo.MaxLinhasPorMensagem {
			t.Errorf("mensagem com %d linhas", len(parte))
		}
		for _, l := range parte {
			if n := len([]rune(l)); n > protocolo.MaxCaracteresPorLinha {
				t.Errorf("linha com %d caracteres", n)
			}
		}
		total += len(parte)
	}
	// A linha longa vira três; as outras seguem iguais.
	if esperado := 3 + protocolo.MaxLinhasPorMensagem + 10; total != esperado {
		t.Errorf("total = %d, esperado %d", total, esperado)
	}
	if partes[0][0]+partes[0][1]+partes[0][2] != longa {
		t.Error("a linha longa não foi reconstituída na ordem")
	}
	if Dividir(nil) != nil {
		t.Error("lista vazia não deveria gerar mensagem")
	}
}

func TestFerramentaAusenteEAmbienteInvalido(t *testing.T) {
	g, c := preparar(t, map[string]string{
		"coleta/main.py":     "print('não deveria rodar')\n",
		"coleta/poetry.lock": "",
	})
	g.op.Programas.Poetry = "poetry-que-nao-existe"

	g.Atender(iniciar(30, "coleta/main.py", 30))
	fim := c.esperarFim(t, 30)

	if fim.Motivo != protocolo.AmbienteInvalido || fim.CodigoSaida != nil {
		t.Fatalf("fim = %+v", fim)
	}
	todas := c.linhasComAmbiente(30)
	if ultima := todas[len(todas)-1]; !strings.Contains(ultima, "não está instalado nesta máquina") {
		t.Errorf("última linha = %q", ultima)
	}
	if len(c.linhas(30)) != 0 {
		t.Errorf("o robô não deveria ter rodado: %q", c.linhas(30))
	}
}

func TestRequirementsRodaNoProprioVenv(t *testing.T) {
	g, c := preparar(t, map[string]string{
		"coleta/main.py":          "import sys\nprint(sys.prefix)\n",
		"coleta/requirements.txt": "# sem dependências\n",
	})
	venvs := t.TempDir()
	g.op.PastaVenvs = venvs

	g.Atender(iniciar(31, "coleta/main.py", 60))
	fim := c.esperarFim(t, 31)

	if fim.Motivo != protocolo.Concluido || fim.CodigoSaida == nil || *fim.CodigoSaida != 0 {
		t.Fatalf("fim = %+v, linhas = %q", fim, c.linhasComAmbiente(31))
	}
	saida := c.linhas(31)
	pastaDoRobo, _ := filepath.EvalSymlinks(filepath.Join(g.op.PastaRobos, "coleta"))
	esperado := filepath.Join(venvs, ambiente.NomeDoVenv(g.op.PastaRobos, pastaDoRobo))
	if ultima := saida[len(saida)-1]; ultima != esperado {
		t.Errorf("rodou com %q, esperado o venv do robô", ultima)
	}
}

func TestPreparoQueFalhaEPreparoFalhou(t *testing.T) {
	g, c := preparar(t, map[string]string{
		"coleta/main.py":          "print('não deveria rodar')\n",
		"coleta/requirements.txt": "=== isto não é um requisito\n",
	})
	g.op.PastaVenvs = t.TempDir()

	g.Atender(iniciar(32, "coleta/main.py", 60))
	fim := c.esperarFim(t, 32)

	if fim.Motivo != protocolo.PreparoFalhou {
		t.Fatalf("fim = %+v", fim)
	}
	todas := c.linhasComAmbiente(32)
	if ultima := todas[len(todas)-1]; !strings.HasPrefix(ultima, ambiente.Prefixo+" preparo falhou") {
		t.Errorf("última linha = %q", ultima)
	}
}
