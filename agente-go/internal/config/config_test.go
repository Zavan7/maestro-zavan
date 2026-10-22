package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func definir(t *testing.T, url, token, pasta string) {
	t.Helper()
	t.Setenv("MAESTRO_URL", url)
	t.Setenv("MAESTRO_TOKEN", token)
	t.Setenv("AGENTE_PASTA_ROBOS", pasta)
	t.Setenv("AGENTE_UV", "")
	t.Setenv("AGENTE_PYTHON", "")
	t.Setenv("AGENTE_PASTA_VENVS", "")
	t.Setenv("AGENTE_USUARIO_ROBOS", "")
	t.Setenv("AGENTE_PERMITIR_WS_SEM_TLS", "")
}

func TestCarregarValidaEAplicaPadroes(t *testing.T) {
	pasta := t.TempDir()
	definir(t, " ws://localhost:8000/ws/agente/ ", "mae_abc", pasta)

	cfg, err := Carregar()

	if err != nil {
		t.Fatalf("erro inesperado: %v", err)
	}
	if cfg.URL != "ws://localhost:8000/ws/agente/" || cfg.PastaRobos != pasta {
		t.Errorf("cfg = %+v", cfg)
	}
	if cfg.UV != "uv" || cfg.Python != "python3" {
		t.Errorf("padrões = %q, %q", cfg.UV, cfg.Python)
	}
}

func TestCarregarAceitaUvEPythonDoAmbiente(t *testing.T) {
	definir(t, "wss://maestro/ws/agente/", "mae_abc", t.TempDir())
	t.Setenv("AGENTE_UV", "/opt/uv")
	t.Setenv("AGENTE_PYTHON", "/usr/bin/python3.14")

	cfg, err := Carregar()

	if err != nil || cfg.UV != "/opt/uv" || cfg.Python != "/usr/bin/python3.14" {
		t.Fatalf("cfg = %+v, err = %v", cfg, err)
	}
}

func TestCarregarJuntaTodosOsProblemas(t *testing.T) {
	definir(t, "http://localhost:8000/", "sem_prefixo", "/nao/existe/mesmo")

	_, err := Carregar()

	if err == nil {
		t.Fatal("esperava erro")
	}
	for _, trecho := range []string{"MAESTRO_URL", "MAESTRO_TOKEN", "AGENTE_PASTA_ROBOS"} {
		if !strings.Contains(err.Error(), trecho) {
			t.Errorf("erro não cita %s: %v", trecho, err)
		}
	}
}

func TestCarregarSemNadaDefinido(t *testing.T) {
	definir(t, "", "", "")

	_, err := Carregar()

	if err == nil || !strings.Contains(err.Error(), "não definida") {
		t.Fatalf("err = %v", err)
	}
}

func TestCarregarCriaAPastaDeVenvs(t *testing.T) {
	definir(t, "ws://localhost:8000/ws/agente/", "mae_abc", t.TempDir())
	venvs := filepath.Join(t.TempDir(), "venvs")
	t.Setenv("AGENTE_PASTA_VENVS", venvs)

	cfg, err := Carregar()

	if err != nil || cfg.PastaVenvs != venvs {
		t.Fatalf("cfg = %+v, err = %v", cfg, err)
	}
	if info, err := os.Stat(venvs); err != nil || !info.IsDir() {
		t.Errorf("pasta de venvs não criada: %v", err)
	}
}

func TestCarregarRecusaPastaDeVenvsRelativa(t *testing.T) {
	definir(t, "ws://localhost:8000/ws/agente/", "mae_abc", t.TempDir())
	t.Setenv("AGENTE_PASTA_VENVS", "venvs")

	if _, err := Carregar(); err == nil || !strings.Contains(err.Error(), "AGENTE_PASTA_VENVS") {
		t.Fatalf("err = %v", err)
	}
}

func TestWsSemTLSSoNaMaquinaLocalOuComPermissao(t *testing.T) {
	casos := []struct {
		url, permitir string
		valida        bool
	}{
		{"ws://localhost:8000/ws/agente/", "", true},
		{"ws://127.0.0.1:8000/ws/agente/", "", true},
		{"ws://[::1]:8000/ws/agente/", "", true},
		{"wss://maestro.exemplo.com/ws/agente/", "", true},
		{"ws://maestro.exemplo.com/ws/agente/", "", false},
		{"ws://192.168.0.10:8000/ws/agente/", "", false},
		{"ws://web:8000/ws/agente/", "1", true},
	}
	for _, caso := range casos {
		definir(t, caso.url, "mae_abc", t.TempDir())
		t.Setenv("AGENTE_PERMITIR_WS_SEM_TLS", caso.permitir)

		_, err := Carregar()

		if (err == nil) != caso.valida {
			t.Errorf("%s (permitir=%q): err = %v", caso.url, caso.permitir, err)
		}
	}
}

func TestUsuarioDosRobos(t *testing.T) {
	definir(t, "ws://localhost/ws/agente/", "mae_abc", t.TempDir())
	t.Setenv("AGENTE_USUARIO_ROBOS", "1001:1002")

	cfg, err := Carregar()

	if os.Geteuid() != 0 {
		if err == nil || !strings.Contains(err.Error(), "root") {
			t.Fatalf("sem root deveria recusar: %v", err)
		}
		return
	}
	if err != nil || cfg.UsuarioRobos == nil || cfg.UsuarioRobos.UID != 1001 || cfg.UsuarioRobos.GID != 1002 {
		t.Fatalf("cfg = %+v, err = %v", cfg.UsuarioRobos, err)
	}
	t.Setenv("AGENTE_USUARIO_ROBOS", "usuario-que-nao-existe")
	if _, err := Carregar(); err == nil {
		t.Error("usuário inexistente deveria ser recusado")
	}
}
