// Package config lê a configuração do agente a partir do ambiente.
package config

import (
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

// Config reúne tudo o que o agente precisa para trabalhar.
type Config struct {
	// URL do WebSocket do Maestro, como ws://localhost:8000/ws/agente/.
	URL string
	// Token gerado em configurações → agentes; começa com "mae_".
	Token string
	// PastaRobos é a pasta aprovada: só robôs dentro dela rodam.
	PastaRobos string
	// UV roda os robôs que têm pyproject.toml na pasta (padrão "uv").
	UV string
	// Python roda os robôs sem pyproject.toml (padrão "python3").
	Python string
	// PastaVenvs, se definida, guarda o ambiente de cada robô fora da
	// pasta dele (opcional). Usada no Docker, onde o .venv da pasta do
	// robô foi criado pelo Python do host e não serve no container.
	PastaVenvs string
}

// Carregar lê MAESTRO_URL, MAESTRO_TOKEN e AGENTE_PASTA_ROBOS e confere
// cada um; AGENTE_UV, AGENTE_PYTHON e AGENTE_PASTA_VENVS são opcionais. Devolve todos os problemas de uma vez, para quem configura
// não precisar corrigir um por um.
func Carregar() (Config, error) {
	cfg := Config{
		URL:        strings.TrimSpace(os.Getenv("MAESTRO_URL")),
		Token:      strings.TrimSpace(os.Getenv("MAESTRO_TOKEN")),
		PastaRobos: strings.TrimSpace(os.Getenv("AGENTE_PASTA_ROBOS")),
		UV:         padrao(os.Getenv("AGENTE_UV"), "uv"),
		Python:     padrao(os.Getenv("AGENTE_PYTHON"), "python3"),
		PastaVenvs: strings.TrimSpace(os.Getenv("AGENTE_PASTA_VENVS")),
	}

	var problemas []error

	if cfg.URL == "" {
		problemas = append(problemas, errors.New("MAESTRO_URL não definida"))
	} else if u, err := url.Parse(cfg.URL); err != nil ||
		(u.Scheme != "ws" && u.Scheme != "wss") {
		problemas = append(problemas,
			fmt.Errorf("MAESTRO_URL precisa começar com ws:// ou wss://: %q", cfg.URL))
	}

	if !strings.HasPrefix(cfg.Token, "mae_") {
		problemas = append(problemas,
			errors.New("MAESTRO_TOKEN ausente ou inválido (começa com mae_)"))
	}

	if cfg.PastaRobos == "" {
		problemas = append(problemas, errors.New("AGENTE_PASTA_ROBOS não definida"))
	} else {
		absoluta, err := filepath.Abs(cfg.PastaRobos)
		if err == nil {
			cfg.PastaRobos = absoluta
		}
		info, err := os.Stat(cfg.PastaRobos)
		if err != nil || !info.IsDir() {
			problemas = append(problemas,
				fmt.Errorf("AGENTE_PASTA_ROBOS não é uma pasta: %q", cfg.PastaRobos))
		}
	}

	if cfg.PastaVenvs != "" {
		if !filepath.IsAbs(cfg.PastaVenvs) {
			problemas = append(problemas,
				fmt.Errorf("AGENTE_PASTA_VENVS precisa ser um caminho absoluto: %q", cfg.PastaVenvs))
		} else if err := os.MkdirAll(cfg.PastaVenvs, 0o755); err != nil {
			problemas = append(problemas,
				fmt.Errorf("AGENTE_PASTA_VENVS não pôde ser criada: %w", err))
		}
	}

	return cfg, errors.Join(problemas...)
}

// padrao devolve valor sem espaços nas pontas, ou alternativa se vazio.
func padrao(valor, alternativa string) string {
	if v := strings.TrimSpace(valor); v != "" {
		return v
	}
	return alternativa
}
