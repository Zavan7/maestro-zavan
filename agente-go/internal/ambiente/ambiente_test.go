package ambiente

import (
	"os"
	"path/filepath"
	"slices"
	"testing"
)

func gravar(t *testing.T, pasta string, arquivos map[string]string) {
	t.Helper()
	for nome, conteudo := range arquivos {
		if err := os.WriteFile(filepath.Join(pasta, nome), []byte(conteudo), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

func TestDetectarCadaFerramentaPelosArquivos(t *testing.T) {
	poetry := "[tool.poetry]\nname = \"x\"\n"
	casos := []struct {
		arquivos map[string]string
		esperada Ferramenta
	}{
		{map[string]string{"uv.lock": "", "pyproject.toml": poetry}, UV},
		{map[string]string{"poetry.lock": ""}, Poetry},
		{map[string]string{"pdm.lock": ""}, PDM},
		{map[string]string{"Pipfile": ""}, Pipenv},
		{map[string]string{"pyproject.toml": poetry}, Poetry},
		{map[string]string{"pyproject.toml": "[tool.poetry.dependencies]\n"}, Poetry},
		{map[string]string{"pyproject.toml": "[tool.pdm]\n"}, PDM},
		{map[string]string{"pyproject.toml": "[project]\nname = \"x\"\n"}, UV},
		{map[string]string{"requirements.txt": "six\n"}, Pip},
		{map[string]string{}, Sistema},
	}
	for _, caso := range casos {
		pasta := t.TempDir()
		gravar(t, pasta, caso.arquivos)
		if got, _ := Detectar(pasta); got != caso.esperada {
			t.Errorf("Detectar(%v) = %s, esperado %s", caso.arquivos, got, caso.esperada)
		}
	}
}

func TestNomeDoVenvVemDoCaminhoDoRobo(t *testing.T) {
	robos := t.TempDir()
	real, _ := filepath.EvalSymlinks(robos)
	casos := map[string]string{
		filepath.Join(real, "patrice", "desafio_rpa"): "patrice__desafio_rpa",
		real: "_raiz",
	}
	for pasta, esperado := range casos {
		if got := NomeDoVenv(robos, pasta); got != esperado {
			t.Errorf("NomeDoVenv(%q) = %q, esperado %q", pasta, got, esperado)
		}
	}
}

func TestAmbienteLimpoNaoVazaVenvNemToken(t *testing.T) {
	limpo := AmbienteLimpo([]string{
		"PATH=/opt/venv/bin:/usr/bin",
		"VIRTUAL_ENV=/opt/venv",
		"UV_PROJECT_ENVIRONMENT=/outro",
		"MAESTRO_TOKEN=mae_x",
		"HOME=/home/robo",
	})
	esperado := []string{"PATH=/usr/bin", "HOME=/home/robo", "PYTHONUNBUFFERED=1"}
	if !slices.Equal(limpo, esperado) {
		t.Errorf("ambiente = %q", limpo)
	}
}

func TestPlanejarGuardaCadaAmbienteForaDaPasta(t *testing.T) {
	programas := Programas{UV: "uv", Poetry: "poetry", PDM: "pdm", Pipenv: "pipenv", Python: "python3"}
	casos := map[string]string{
		"uv.lock":      "UV_PROJECT_ENVIRONMENT=",
		"poetry.lock":  "POETRY_VIRTUALENVS_PATH=",
		"Pipfile.lock": "WORKON_HOME=",
	}
	for arquivo, variavel := range casos {
		robos := t.TempDir()
		pasta := filepath.Join(robos, "coleta")
		if err := os.Mkdir(pasta, 0o755); err != nil {
			t.Fatal(err)
		}
		gravar(t, pasta, map[string]string{arquivo: ""})

		plano := Planejar(filepath.Join(pasta, "main.py"), programas, robos, "/venvs")

		if !slices.Contains(plano.Env, variavel+"/venvs/coleta") {
			t.Errorf("%s: env = %q, esperado %s/venvs/coleta", arquivo, plano.Env, variavel)
		}
	}
}

func TestPipenvSincronizaComLockEInstalaSem(t *testing.T) {
	pasta := t.TempDir()
	gravar(t, pasta, map[string]string{"Pipfile": ""})
	programas := Programas{Pipenv: "pipenv"}
	script := filepath.Join(pasta, "main.py")

	if got := Planejar(script, programas, pasta, "").Preparo; !slices.Equal(got[0], []string{"pipenv", "install"}) {
		t.Errorf("sem lock: %q", got)
	}
	gravar(t, pasta, map[string]string{"Pipfile.lock": "{}"})
	if got := Planejar(script, programas, pasta, "").Preparo; !slices.Equal(got[0], []string{"pipenv", "sync"}) {
		t.Errorf("com lock: %q", got)
	}
}

func TestComandoRodaPythonSemBufferNoAmbiente(t *testing.T) {
	plano := Plano{Python: []string{"poetry", "run", "python"}}

	got := plano.Comando("/robos/main.py")

	if !slices.Equal(got, []string{"poetry", "run", "python", "-u", "/robos/main.py"}) {
		t.Errorf("comando = %q", got)
	}
}
