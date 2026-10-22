// Package config lê a configuração do agente a partir do ambiente.
package config

import (
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"os/user"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/ambiente"
	"github.com/Zavan7/maestro-zavan/agente-go/internal/executor"
)

// Config reúne tudo o que o agente precisa para trabalhar.
type Config struct {
	// URL do WebSocket do Maestro, como ws://localhost:8000/ws/agente/.
	URL string
	// Token gerado em configurações → agentes; começa com "mae_".
	Token string
	// PastaRobos é a pasta aprovada: só robôs dentro dela rodam.
	PastaRobos string
	// UV roda os robôs com uv.lock ou pyproject.toml (padrão "uv").
	UV string
	// Python roda os robôs sem gerenciador de dependências e cria o venv
	// dos que só têm requirements.txt (padrão "python3").
	Python string
	// Poetry, PDM e Pipenv rodam os robôs que usam cada ferramenta
	// (padrão: o nome dela, procurado no PATH).
	Poetry string
	PDM    string
	Pipenv string
	// UsuarioRobos, se definido, é o usuário do sistema com que os robôs
	// rodam, diferente do agente (opcional; exige agente como root).
	UsuarioRobos *executor.Usuario
	// PastaVenvs, se definida, guarda o ambiente de cada robô fora da
	// pasta dele (opcional). Usada no Docker, onde o .venv da pasta do
	// robô foi criado pelo Python do host e não serve no container.
	PastaVenvs string
}

// Carregar lê MAESTRO_URL, MAESTRO_TOKEN e AGENTE_PASTA_ROBOS e confere
// cada um; AGENTE_UV, AGENTE_POETRY, AGENTE_PDM, AGENTE_PIPENV,
// AGENTE_PYTHON e AGENTE_PASTA_VENVS são opcionais. Devolve todos os
// problemas de uma vez, para quem configura não precisar corrigir um
// por um.
func Carregar() (Config, error) {
	cfg, erroAmbiente := CarregarAmbiente()
	cfg.URL = strings.TrimSpace(os.Getenv("MAESTRO_URL"))
	cfg.Token = strings.TrimSpace(os.Getenv("MAESTRO_TOKEN"))

	var problemas []error
	if cfg.URL == "" {
		problemas = append(problemas, errors.New("MAESTRO_URL não definida"))
	} else if u, err := url.Parse(cfg.URL); err != nil ||
		(u.Scheme != "ws" && u.Scheme != "wss") {
		problemas = append(problemas,
			fmt.Errorf("MAESTRO_URL precisa começar com ws:// ou wss://: %q", cfg.URL))
	} else if u.Scheme == "ws" && !local(u.Hostname()) &&
		!semTLSPermitido(os.Getenv("AGENTE_PERMITIR_WS_SEM_TLS")) {
		// Sem TLS, o token viaja em texto e qualquer um no caminho o
		// copia. ws:// só vale na própria máquina, ou com permissão
		// explícita numa rede interna (como a do Docker).
		problemas = append(problemas,
			fmt.Errorf("MAESTRO_URL com ws:// fora da máquina local expõe o token: use wss:// "+
				"(ou AGENTE_PERMITIR_WS_SEM_TLS=1 numa rede interna): %q", cfg.URL))
	}
	if !strings.HasPrefix(cfg.Token, "mae_") {
		problemas = append(problemas,
			errors.New("MAESTRO_TOKEN ausente ou inválido (começa com mae_)"))
	}
	return cfg, errors.Join(append(problemas, erroAmbiente)...)
}

// CarregarAmbiente lê só o que é preciso para preparar e rodar robôs
// (pasta aprovada, programas e pasta dos venvs), sem a conexão. É o que
// o subcomando "agente ambiente" usa.
func CarregarAmbiente() (Config, error) {
	cfg := Config{
		PastaRobos: strings.TrimSpace(os.Getenv("AGENTE_PASTA_ROBOS")),
		UV:         padrao(os.Getenv("AGENTE_UV"), "uv"),
		Python:     padrao(os.Getenv("AGENTE_PYTHON"), "python3"),
		Poetry:     padrao(os.Getenv("AGENTE_POETRY"), "poetry"),
		PDM:        padrao(os.Getenv("AGENTE_PDM"), "pdm"),
		Pipenv:     padrao(os.Getenv("AGENTE_PIPENV"), "pipenv"),
		PastaVenvs: strings.TrimSpace(os.Getenv("AGENTE_PASTA_VENVS")),
	}

	var problemas []error
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

	if texto := strings.TrimSpace(os.Getenv("AGENTE_USUARIO_ROBOS")); texto != "" {
		usuario, err := lerUsuario(texto)
		switch {
		case err != nil:
			problemas = append(problemas, fmt.Errorf("AGENTE_USUARIO_ROBOS: %w", err))
		case os.Geteuid() != 0:
			problemas = append(problemas,
				errors.New("AGENTE_USUARIO_ROBOS exige o agente rodando como root"))
		default:
			cfg.UsuarioRobos = usuario
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

// Programas devolve os executáveis de cada gerenciador de dependências.
func (c Config) Programas() ambiente.Programas {
	return ambiente.Programas{UV: c.UV, Poetry: c.Poetry, PDM: c.PDM, Pipenv: c.Pipenv, Python: c.Python}
}

// local diz se o host é a própria máquina.
func local(host string) bool {
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

// semTLSPermitido lê AGENTE_PERMITIR_WS_SEM_TLS como booleano.
func semTLSPermitido(valor string) bool {
	permitido, _ := strconv.ParseBool(strings.TrimSpace(valor))
	return permitido
}

// lerUsuario lê "uid:gid" ou o nome de um usuário do sistema (o grupo é
// o principal dele).
func lerUsuario(texto string) (*executor.Usuario, error) {
	if uid, gid, ok := strings.Cut(texto, ":"); ok {
		u, err1 := strconv.ParseUint(uid, 10, 32)
		g, err2 := strconv.ParseUint(gid, 10, 32)
		if err1 != nil || err2 != nil {
			return nil, fmt.Errorf("use uid:gid ou o nome do usuário: %q", texto)
		}
		return &executor.Usuario{UID: uint32(u), GID: uint32(g)}, nil
	}
	registro, err := user.Lookup(texto)
	if err != nil {
		return nil, err
	}
	u, err1 := strconv.ParseUint(registro.Uid, 10, 32)
	g, err2 := strconv.ParseUint(registro.Gid, 10, 32)
	if err1 != nil || err2 != nil {
		return nil, fmt.Errorf("usuário %q sem uid numérico", texto)
	}
	return &executor.Usuario{UID: uint32(u), GID: uint32(g)}, nil
}

// padrao devolve valor sem espaços nas pontas, ou alternativa se vazio.
func padrao(valor, alternativa string) string {
	if v := strings.TrimSpace(valor); v != "" {
		return v
	}
	return alternativa
}
