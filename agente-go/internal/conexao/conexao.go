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

	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
)

const (
	intervaloHeartbeat = 30 * time.Second
	esperaMaxima       = 30 * time.Second
	prazoEscrita       = 10 * time.Second
	prazoFechamento    = 2 * time.Second

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

// Cliente é a conexão do agente com o Maestro.
type Cliente struct {
	url       string
	token     string
	logger    *slog.Logger
	aoReceber func(protocolo.Recebida)
	saida     *fila
}

// Novo cria um Cliente para o endereço e o token informados. aoReceber
// é chamada com cada comando do Maestro, na goroutine de leitura: ela
// não pode demorar (o gerente de execuções roda cada robô à parte).
func Novo(url, token string, logger *slog.Logger, aoReceber func(protocolo.Recebida)) *Cliente {
	return &Cliente{
		url:       url,
		token:     token,
		logger:    logger,
		aoReceber: aoReceber,
		saida:     novaFila(LimiteFila),
	}
}

// Enviar coloca uma mensagem na fila de saída. Pode ser chamada de
// qualquer goroutine, com ou sem conexão aberta: o que não sair agora
// sai depois de reconectar.
func (c *Cliente) Enviar(v any) {
	if !c.saida.por(v) {
		c.logger.Warn("fila de saída cheia; linhas de log descartadas", "limite", LimiteFila)
	}
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
	// duas escritas ao mesmo tempo. Quem quiser enviar algo usa a fila.
	go c.escrever(ctxConversa, conn)

	// Ctrl+C: avisa o Maestro com um fechamento educado; isso faz a
	// leitura abaixo terminar.
	go func() {
		<-ctxConversa.Done()
		if ctx.Err() != nil {
			fechamento := websocket.FormatCloseMessage(websocket.CloseNormalClosure, "agente desligando")
			_ = conn.WriteControl(websocket.CloseMessage, fechamento, time.Now().Add(time.Second))
			// Se o Maestro não responder ao fechamento, não fica
			// esperando para sempre.
			time.AfterFunc(prazoFechamento, func() { _ = conn.Close() })
		}
	}()

	for {
		var msg protocolo.Recebida
		if err := conn.ReadJSON(&msg); err != nil {
			return true, traduzirFechamento(err)
		}
		c.aoReceber(msg)
	}
}

// escrever é a única goroutine que escreve na conexão. Ela esvazia a
// fila de saída e, a cada 30 s, manda o heartbeat.
func (c *Cliente) escrever(ctx context.Context, conn *websocket.Conn) {
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

	// Uma mensagem só sai da fila depois de escrita: se a escrita
	// falhar, ela continua lá e vai na próxima conexão.
	esvaziar := func() bool {
		for {
			v, tem := c.saida.primeiro()
			if !tem {
				return true
			}
			if !enviar(v) {
				return false
			}
			c.saida.tirar()
		}
	}

	// Um sinal logo ao conectar: o painel mostra o agente online na hora.
	// Depois, o que ficou na fila enquanto o agente estava sem conexão.
	if !enviar(protocolo.NovoHeartbeat()) {
		return
	}
	if pendentes := c.saida.tamanho(); pendentes > 0 {
		c.logger.Info("reenviando mensagens pendentes", "quantidade", pendentes)
	}
	if !esvaziar() {
		return
	}
	for {
		select {
		case <-ctx.Done():
			return
		case <-relogio.C:
			if !enviar(protocolo.NovoHeartbeat()) {
				return
			}
		case <-c.saida.aviso:
			if !esvaziar() {
				return
			}
		}
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
