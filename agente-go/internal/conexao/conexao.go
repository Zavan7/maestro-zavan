// Package conexao mantém o agente conectado ao Maestro: abre o WebSocket,
// manda o heartbeat, reconecta quando cai e entrega os comandos recebidos.
package conexao

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/gorilla/websocket"
)

const (
	intervaloHeartbeat = 30 * time.Second
	esperaMaxima       = 30 * time.Second
	prazoEscrita       = 10 * time.Second

	// Códigos de fechamento definidos em docs/agente/protocolo.md.
	codigoTokenRevogado = 4401
	codigoSubstituido   = 4409
)

// ErrTokenRecusado indica que o Maestro recusou o token (HTTP 403).
// Tentar de novo com o mesmo token não adianta.
var ErrTokenRecusado = errors.New("o Maestro recusou o token (403)")

// ErrSubstituido indica que outra conexão abriu com o mesmo token.
// Reconectar faria os dois agentes se derrubarem para sempre.
var ErrSubstituido = errors.New("outra conexão abriu com o mesmo token (4409)")

// Mensagem é o envelope comum: todo JSON do protocolo tem o campo "tipo".
type Mensagem struct {
	Tipo string `json:"tipo"`
}

// Recebida guarda os campos que o agente lê dos comandos do Maestro.
type Recebida struct {
	Tipo            string `json:"tipo"`
	ExecucaoID      int64  `json:"execucao_id"`
	Robo            string `json:"robo"`
	TimeoutSegundos int    `json:"timeout_segundos"`
	Mensagem        string `json:"mensagem"`
}

// Cliente é a conexão do agente com o Maestro.
type Cliente struct {
	url    string
	token  string
	logger *slog.Logger
}

// Novo cria um Cliente para o endereço e o token informados.
func Novo(url, token string, logger *slog.Logger) *Cliente {
	return &Cliente{url: url, token: token, logger: logger}
}

// Rodar conecta e reconecta até o contexto ser cancelado ou acontecer um
// erro definitivo (ErrTokenRecusado, ErrSubstituido). Entre tentativas,
// espera 1 s, 2 s, 4 s... até 30 s, e volta a 1 s depois de conectar.
func (c *Cliente) Rodar(ctx context.Context) error {
	espera := time.Second
	for {
		conectou, err := c.conversar(ctx)
		if ctx.Err() != nil {
			return nil // desligamento pedido (Ctrl+C, systemd)
		}
		if errors.Is(err, ErrTokenRecusado) || errors.Is(err, ErrSubstituido) {
			return err
		}
		if conectou {
			espera = time.Second
		}
		c.logger.Warn("sem conexão com o Maestro", "erro", err, "nova_tentativa_em", espera)

		select {
		case <-ctx.Done():
			return nil
		case <-time.After(espera):
		}
		espera = min(espera*2, esperaMaxima)
	}
}

// conversar abre uma conexão e a atende até ela cair. O booleano diz se
// a conexão chegou a abrir, para o Rodar saber se zera a espera.
func (c *Cliente) conversar(ctx context.Context) (bool, error) {
	cabecalhos := http.Header{"Authorization": {"Bearer " + c.token}}
	conn, resp, err := websocket.DefaultDialer.DialContext(ctx, c.url, cabecalhos)
	if err != nil {
		if resp != nil && resp.StatusCode == http.StatusForbidden {
			return false, ErrTokenRecusado
		}
		return false, err
	}
	defer conn.Close()
	c.logger.Info("conectado ao Maestro", "url", c.url)

	// Quando esta conversa acabar (por qualquer motivo), o escritor para.
	ctxConversa, encerrar := context.WithCancel(ctx)
	defer encerrar()

	// Só uma goroutine escreve na conexão: o gorilla/websocket não aceita
	// duas escritas ao mesmo tempo. Quem quiser enviar algo usa o canal.
	saida := make(chan any, 64)
	go c.escrever(ctxConversa, conn, saida)

	// Ctrl+C: avisa o Maestro com um fechamento educado; isso faz a
	// leitura abaixo terminar.
	go func() {
		<-ctxConversa.Done()
		if ctx.Err() != nil {
			fechamento := websocket.FormatCloseMessage(websocket.CloseNormalClosure, "agente desligando")
			_ = conn.WriteControl(websocket.CloseMessage, fechamento, time.Now().Add(time.Second))
		}
	}()

	for {
		var msg Recebida
		if err := conn.ReadJSON(&msg); err != nil {
			return true, traduzirFechamento(err)
		}
		c.atender(msg)
	}
}

// escrever é a única goroutine que escreve na conexão. Ela envia o que
// chega pelo canal e, a cada 30 s, o heartbeat.
func (c *Cliente) escrever(ctx context.Context, conn *websocket.Conn, saida <-chan any) {
	relogio := time.NewTicker(intervaloHeartbeat)
	defer relogio.Stop()

	enviar := func(v any) bool {
		_ = conn.SetWriteDeadline(time.Now().Add(prazoEscrita))
		if err := conn.WriteJSON(v); err != nil {
			c.logger.Warn("falha ao enviar", "erro", err)
			_ = conn.Close() // derruba a leitura, que dispara a reconexão
			return false
		}
		return true
	}

	// Um sinal logo ao conectar: o painel mostra o agente online na hora.
	if !enviar(Mensagem{Tipo: "heartbeat"}) {
		return
	}
	for {
		select {
		case <-ctx.Done():
			return
		case <-relogio.C:
			if !enviar(Mensagem{Tipo: "heartbeat"}) {
				return
			}
		case v := <-saida:
			if !enviar(v) {
				return
			}
		}
	}
}

// atender trata um comando do Maestro. Neste passo só registra o que
// chegou; iniciar e parar entram nos próximos passos.
func (c *Cliente) atender(msg Recebida) {
	switch msg.Tipo {
	case "erro":
		// O Maestro só manda "erro" quando o agente fere o protocolo:
		// é bug do agente, então vai para o log como erro.
		c.logger.Error("o Maestro apontou erro de protocolo", "mensagem", msg.Mensagem)
	case "iniciar", "parar":
		c.logger.Info("comando recebido (ainda não implementado)",
			"tipo", msg.Tipo, "execucao_id", msg.ExecucaoID, "robo", msg.Robo)
	default:
		c.logger.Warn("mensagem de tipo desconhecido ignorada", "tipo", msg.Tipo)
	}
}

// traduzirFechamento transforma os códigos de fechamento do protocolo em
// erros com significado.
func traduzirFechamento(err error) error {
	var fechamento *websocket.CloseError
	if errors.As(err, &fechamento) {
		switch fechamento.Code {
		case codigoSubstituido:
			return ErrSubstituido
		case codigoTokenRevogado:
			// Reconecta: se o token não vale mais, o aperto de mão
			// devolve 403 e o agente para com a mensagem certa.
			return fmt.Errorf("token trocado ou agente desativado (4401): %w", err)
		}
	}
	return err
}
