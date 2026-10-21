// Comando agente-go é o agente do Maestro: roda na máquina dos robôs,
// conecta no Maestro por WebSocket e executa o que ele mandar.
//
// Configuração por variáveis de ambiente:
//
//	MAESTRO_URL=ws://localhost:8000/ws/agente/
//	MAESTRO_TOKEN=mae_...
//	AGENTE_PASTA_ROBOS=/caminho/dos/robos
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/conexao"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/config"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))

	cfg, err := config.Carregar()
	if err != nil {
		logger.Error("configuração inválida", "erro", err)
		os.Exit(2)
	}

	// Ctrl+C (SIGINT) ou o systemd parando o serviço (SIGTERM) cancelam
	// o contexto, e tudo que depende dele encerra em ordem.
	ctx, parar := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer parar()

	logger.Info("agente iniciando", "url", cfg.URL, "pasta_robos", cfg.PastaRobos)
	if err := conexao.Novo(cfg.URL, cfg.Token, logger).Rodar(ctx); err != nil {
		logger.Error("agente encerrado", "erro", err)
		os.Exit(1)
	}
	logger.Info("agente encerrado")
}
