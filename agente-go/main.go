// Comando agente-go é o agente do Maestro: roda na máquina dos robôs,
// conecta no Maestro por WebSocket e executa o que ele mandar.
//
// Configuração por variáveis de ambiente:
//
//	MAESTRO_URL=ws://localhost:8000/ws/agente/
//	MAESTRO_TOKEN=mae_...
//	AGENTE_PASTA_ROBOS=/caminho/dos/robos
//	AGENTE_UV=uv            (opcional; robôs com uv.lock ou pyproject.toml)
//	AGENTE_POETRY=poetry    (opcional; robôs com poetry.lock ou [tool.poetry])
//	AGENTE_PDM=pdm          (opcional; robôs com pdm.lock ou [tool.pdm])
//	AGENTE_PIPENV=pipenv    (opcional; robôs com Pipfile)
//	AGENTE_PYTHON=python3   (opcional; robôs com requirements.txt ou sem gerenciador)
//	AGENTE_PASTA_VENVS=/var/lib/agente/venvs  (opcional; venv de cada robô fora da pasta dele)
//	AGENTE_USUARIO_ROBOS=robo  (opcional; usuário dos robôs, "nome" ou "uid:gid"; exige root)
//	AGENTE_PERMITIR_WS_SEM_TLS=1  (opcional; aceita ws:// fora da máquina local, numa rede interna)
//
// O gerenciador de dependências de cada robô (uv, poetry, pdm, pipenv ou
// pip) é detectado pela pasta dele; veja docs/agente/protocolo.md.
//
// Subcomando, para preparar o ambiente de um robô e rodar o Python dele
// à mão (a pasta é relativa a AGENTE_PASTA_ROBOS):
//
//	agente ambiente coleta -- -m playwright install firefox
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/conexao"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/config"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/execucoes"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/protecao"
)

func main() {
	// Antes de tudo: os robôs rodam com o mesmo usuário do agente e, sem
	// isto, leriam o MAESTRO_TOKEN no /proc do agente.
	if err := protecao.ProtegerProcesso(); err != nil {
		fmt.Fprintln(os.Stderr, "aviso: não foi possível proteger o processo:", err)
	}
	if len(os.Args) > 1 && os.Args[1] == "ambiente" {
		os.Exit(rodarAmbiente(os.Args[2:]))
	}
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
		PastaRobos:   cfg.PastaRobos,
		Programas:    cfg.Programas(),
		PastaVenvs:   cfg.PastaVenvs,
		UsuarioRobos: cfg.UsuarioRobos,
		Enviar:       func(v any) { cliente.Enviar(v) },
		Logger:       logger,
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

// rodarAmbiente atende "agente ambiente <pasta do robô> [-- args do python]":
// detecta o gerenciador de dependências da pasta, prepara as
// dependências e, se houver args, roda o Python do robô com eles. A
// pasta é relativa a AGENTE_PASTA_ROBOS e não pode sair dela. Devolve o
// código de saída do processo.
func rodarAmbiente(argumentos []string) int {
	if len(argumentos) == 0 || argumentos[0] == "--" {
		fmt.Fprintln(os.Stderr, "uso: agente ambiente <pasta do robô> [-- argumentos do python]")
		return 2
	}
	pasta, args := argumentos[0], argumentos[1:]
	if len(args) > 0 && args[0] == "--" {
		args = args[1:]
	}

	cfg, err := config.CarregarAmbiente()
	if err != nil {
		fmt.Fprintln(os.Stderr, "configuração inválida:", err)
		return 2
	}
	pastaDoRobo, err := filepath.Abs(filepath.Join(cfg.PastaRobos, pasta))
	if err != nil || !strings.HasPrefix(pastaDoRobo+string(filepath.Separator),
		cfg.PastaRobos+string(filepath.Separator)) {
		fmt.Fprintf(os.Stderr, "%q está fora de %s\n", pasta, cfg.PastaRobos)
		return 2
	}

	gerente := execucoes.Novo(execucoes.Opcoes{
		PastaRobos:   cfg.PastaRobos,
		Programas:    cfg.Programas(),
		PastaVenvs:   cfg.PastaVenvs,
		UsuarioRobos: cfg.UsuarioRobos,
	})
	motivo, codigo := gerente.RodarNoAmbiente(pastaDoRobo, args,
		func(linha string) { fmt.Println(linha) })
	if codigo != nil {
		return *codigo
	}
	fmt.Fprintln(os.Stderr, "não rodou:", motivo)
	return 1
}
