// Comando agente-go é o agente do Maestro: roda na máquina dos robôs,
// conecta no Maestro por WebSocket e executa o que ele mandar.
//
// Configuração por variáveis de ambiente:
//
//	MAESTRO_URL=ws://localhost:8000/ws/agente/
//	MAESTRO_TOKEN=mae_...
//	AGENTE_PASTA_ROBOS=/caminho/dos/robos
//	AGENTE_UV=uv            (opcional; robôs com pyproject.toml)
//	AGENTE_PYTHON=python3   (opcional; robôs sem pyproject.toml)
//	AGENTE_PASTA_VENVS=/var/lib/agente/venvs  (opcional; venv de cada robô fora da pasta dele)
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/conexao"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/config"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/execucoes"
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

	// O gerente manda mensagens pela fila do cliente, e o cliente entrega
	// os comandos ao gerente: um precisa existir antes do outro, por isso
	// a função intermediária.
	var cliente *conexao.Cliente
	gerente := execucoes.Novo(execucoes.Opcoes{
		PastaRobos: cfg.PastaRobos,
		UV:         cfg.UV,
		Python:     cfg.Python,
		PastaVenvs: cfg.PastaVenvs,
		Enviar:     func(v any) { cliente.Enviar(v) },
		Logger:     logger,
	})
	cliente = conexao.Novo(cfg.URL, cfg.Token, logger, gerente.Atender)

	err = cliente.Rodar(ctx)
	// Desligando: nenhum robô fica órfão na máquina.
	gerente.Encerrar()
	if err != nil {
		logger.Error("agente encerrado", "erro", err)
		os.Exit(1)
	}
	logger.Info("agente encerrado")
}
