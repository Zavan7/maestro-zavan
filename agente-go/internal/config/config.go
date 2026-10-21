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
}

// Carregar lê MAESTRO_URL, MAESTRO_TOKEN e AGENTE_PASTA_ROBOS e confere
// cada um. Devolve todos os problemas de uma vez, para quem configura
// não precisar corrigir um por um.
func Carregar() (Config, error) {
	cfg := Config{
		URL:        strings.TrimSpace(os.Getenv("MAESTRO_URL")),
		Token:      strings.TrimSpace(os.Getenv("MAESTRO_TOKEN")),
		PastaRobos: strings.TrimSpace(os.Getenv("AGENTE_PASTA_ROBOS")),
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

	return cfg, errors.Join(problemas...)
}
