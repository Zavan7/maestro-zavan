package conexao

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
)

const tokenValido = "mae_teste"

// maestroFalso aceita conexões com o token válido e entrega cada uma ao
// teste pelo canal conexoes.
type maestroFalso struct {
	servidor *httptest.Server
	conexoes chan *websocket.Conn
}

func novoMaestro(t *testing.T) *maestroFalso {
	t.Helper()
	m := &maestroFalso{conexoes: make(chan *websocket.Conn, 4)}
	var atualizador websocket.Upgrader
	m.servidor = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+tokenValido {
			http.Error(w, "proibido", http.StatusForbidden)
			return
		}
		conn, err := atualizador.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		m.conexoes <- conn
	}))
	t.Cleanup(m.servidor.Close)
	return m
}

func (m *maestroFalso) url() string {
	return "ws" + strings.TrimPrefix(m.servidor.URL, "http")
}

// proxima espera a próxima conexão do agente.
func (m *maestroFalso) proxima(t *testing.T) *websocket.Conn {
	t.Helper()
	select {
	case conn := <-m.conexoes:
		t.Cleanup(func() { conn.Close() })
		return conn
	case <-time.After(5 * time.Second):
		t.Fatal("o agente não conectou")
		return nil
	}
}

// ler devolve a próxima mensagem do agente como mapa.
func ler(t *testing.T, conn *websocket.Conn) map[string]any {
	t.Helper()
	_ = conn.SetReadDeadline(time.Now().Add(5 * time.Second))
	var msg map[string]any
	if err := conn.ReadJSON(&msg); err != nil {
		t.Fatalf("ler: %v", err)
	}
	return msg
}

func silencioso() *slog.Logger { return slog.New(slog.NewTextHandler(io.Discard, nil)) }

// rodar inicia o cliente numa goroutine e devolve o canal do resultado.
func rodar(ctx context.Context, c *Cliente) <-chan error {
	resultado := make(chan error, 1)
	go func() { resultado <- c.Rodar(ctx) }()
	return resultado
}

func esperar(t *testing.T, resultado <-chan error) error {
	t.Helper()
	select {
	case err := <-resultado:
		return err
	case <-time.After(5 * time.Second):
		t.Fatal("Rodar não terminou")
		return nil
	}
}

func TestTokenRecusadoEncerra(t *testing.T) {
	m := novoMaestro(t)
	c := Novo(m.url(), "mae_errado", silencioso(), func(protocolo.Recebida) {})

	err := esperar(t, rodar(context.Background(), c))

	if !errors.Is(err, ErrTokenRecusado) {
		t.Fatalf("err = %v, esperado ErrTokenRecusado", err)
	}
}

func TestHeartbeatAoConectarEComandosEntregues(t *testing.T) {
	m := novoMaestro(t)
	recebidas := make(chan protocolo.Recebida, 1)
	c := Novo(m.url(), tokenValido, silencioso(), func(r protocolo.Recebida) { recebidas <- r })
	ctx, cancelar := context.WithCancel(context.Background())
	resultado := rodar(ctx, c)

	conn := m.proxima(t)
	if msg := ler(t, conn); msg["tipo"] != "heartbeat" {
		t.Fatalf("primeira mensagem = %v", msg)
	}
	comando := map[string]any{"tipo": "iniciar", "execucao_id": 42, "robo": "a/main.py", "timeout_segundos": 300}
	if err := conn.WriteJSON(comando); err != nil {
		t.Fatal(err)
	}
	select {
	case r := <-recebidas:
		if r.Tipo != "iniciar" || r.ExecucaoID != 42 || r.Robo != "a/main.py" || r.TimeoutSegundos != 300 {
			t.Errorf("recebida = %+v", r)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("o comando não chegou")
	}

	cancelar()
	if err := esperar(t, resultado); err != nil {
		t.Errorf("desligamento devolveu %v", err)
	}
}

func TestEnviarMandaNaOrdem(t *testing.T) {
	m := novoMaestro(t)
	c := Novo(m.url(), tokenValido, silencioso(), func(protocolo.Recebida) {})
	ctx, cancelar := context.WithCancel(context.Background())
	defer cancelar()
	rodar(ctx, c)
	conn := m.proxima(t)
	ler(t, conn) // heartbeat

	c.Enviar(protocolo.NovoIniciado(1))
	c.Enviar(protocolo.NovoLog(1, []string{"linha"}))
	c.Enviar(protocolo.NovoFim(1, protocolo.Concluido, nil))

	for _, tipo := range []string{"iniciado", "log", "fim"} {
		if msg := ler(t, conn); msg["tipo"] != tipo {
			t.Fatalf("mensagem = %v, esperado %s", msg, tipo)
		}
	}
}

func TestMensagensDeQuandoEstavaSemConexaoSaemAoReconectar(t *testing.T) {
	m := novoMaestro(t)
	c := Novo(m.url(), tokenValido, silencioso(), func(protocolo.Recebida) {})
	ctx, cancelar := context.WithCancel(context.Background())
	defer cancelar()
	rodar(ctx, c)

	primeira := m.proxima(t)
	ler(t, primeira) // heartbeat
	// O Maestro reinicia: a conexão cai sem fechamento educado.
	primeira.Close()
	time.Sleep(100 * time.Millisecond)

	// Enquanto isso, a execução continua e produz mensagens.
	c.Enviar(protocolo.NovoLog(5, []string{"durante a queda"}))
	codigo := 0
	c.Enviar(protocolo.NovoFim(5, protocolo.Concluido, &codigo))

	segunda := m.proxima(t)
	if msg := ler(t, segunda); msg["tipo"] != "heartbeat" {
		t.Fatalf("primeira mensagem = %v", msg)
	}
	log := ler(t, segunda)
	if log["tipo"] != "log" || log["linhas"].([]any)[0] != "durante a queda" {
		t.Fatalf("log = %v", log)
	}
	fim := ler(t, segunda)
	if fim["tipo"] != "fim" || fim["codigo_saida"] != float64(0) {
		t.Fatalf("fim = %v", fim)
	}
	if c.saida.tamanho() != 0 {
		t.Errorf("fila com %d mensagens depois do reenvio", c.saida.tamanho())
	}
}

func TestSubstituidoEncerra(t *testing.T) {
	m := novoMaestro(t)
	c := Novo(m.url(), tokenValido, silencioso(), func(protocolo.Recebida) {})
	resultado := rodar(context.Background(), c)

	conn := m.proxima(t)
	ler(t, conn)
	fechamento := websocket.FormatCloseMessage(codigoSubstituido, "outra conexão")
	_ = conn.WriteControl(websocket.CloseMessage, fechamento, time.Now().Add(time.Second))

	if err := esperar(t, resultado); !errors.Is(err, ErrSubstituido) {
		t.Fatalf("err = %v, esperado ErrSubstituido", err)
	}
}

func TestFimNuloViraNullNoJSON(t *testing.T) {
	bruto, err := json.Marshal(protocolo.NovoFim(3, protocolo.ScriptInvalido, nil))
	if err != nil {
		t.Fatal(err)
	}
	esperado := `{"tipo":"fim","execucao_id":3,"motivo":"script_invalido","codigo_saida":null}`
	if string(bruto) != esperado {
		t.Errorf("json = %s", bruto)
	}
}

func TestFilaDescartaLogQuandoCheiaMasNuncaOFim(t *testing.T) {
	f := novaFila(2)
	f.por(protocolo.NovoLog(1, []string{"a"}))
	f.por(protocolo.NovoLog(1, []string{"b"}))

	if f.por(protocolo.NovoLog(1, []string{"c"})) {
		t.Error("log aceito com a fila cheia")
	}
	if !f.por(protocolo.NovoFim(1, protocolo.Concluido, nil)) {
		t.Error("fim descartado com a fila cheia")
	}
	if f.tamanho() != 3 {
		t.Errorf("tamanho = %d", f.tamanho())
	}
}

// Garante que Enviar pode ser chamado de várias goroutines ao mesmo
// tempo (o heartbeat e cada execução).
func TestEnviarConcorrente(t *testing.T) {
	c := Novo("ws://nao.usado", tokenValido, silencioso(), func(protocolo.Recebida) {})
	var grupo sync.WaitGroup
	for i := range 50 {
		grupo.Add(1)
		go func() {
			defer grupo.Done()
			c.Enviar(protocolo.NovoIniciado(int64(i)))
		}()
	}
	grupo.Wait()
	if c.saida.tamanho() != 50 {
		t.Errorf("tamanho = %d", c.saida.tamanho())
	}
}
