// Package ambiente descobre qual gerenciador de dependências cada robô
// usa (uv, poetry, pdm, pipenv, pip ou nenhum) e monta como preparar as
// dependências e rodar o robô dentro do ambiente dele.
//
// É a versão em Go de robots/ambiente.py, com a mesma regra, descrita em
// docs/agente/protocolo.md. A detecção olha só a pasta do script, nunca
// as de cima: um robô avulso acharia, subindo, o projeto de outra pessoa.
package ambiente

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
)

// Prefixo marca no log as linhas escritas pelo agente sobre o ambiente.
const Prefixo = "[ambiente]"

// Ferramenta é o gerenciador de dependências de um robô.
type Ferramenta string

const (
	UV      Ferramenta = "uv"
	Poetry  Ferramenta = "poetry"
	PDM     Ferramenta = "pdm"
	Pipenv  Ferramenta = "pipenv"
	Pip     Ferramenta = "pip"
	Sistema Ferramenta = "sistema"
)

// marcadores identificam a ferramenta sozinhos, em ordem de prioridade:
// um lock diz com certeza quem gerencia o projeto.
var marcadores = []struct {
	arquivo    string
	ferramenta Ferramenta
}{
	{"uv.lock", UV},
	{"poetry.lock", Poetry},
	{"pdm.lock", PDM},
	{"Pipfile.lock", Pipenv},
	{"Pipfile", Pipenv},
}

// O robô recebe só estas variáveis do agente, e não o ambiente inteiro:
// o agente tem o MAESTRO_TOKEN e a própria configuração. Uma lista do que
// pode passar não deixa vazar por esquecimento uma variável nova.
// Configuração do próprio robô (usuário e senha de um sistema, por
// exemplo) vai em variáveis com o prefixo ROBO_. É a mesma lista do
// worker (robots/ambiente.py).
var variaveisPermitidas = map[string]bool{
	"PATH": true, "HOME": true, "USER": true, "LOGNAME": true, "SHELL": true, "TERM": true,
	"LANG": true, "LANGUAGE": true, "TZ": true, "TMPDIR": true, "TEMP": true, "TMP": true,
	"DISPLAY": true, "WAYLAND_DISPLAY": true, "XDG_RUNTIME_DIR": true,
	"HTTP_PROXY": true, "HTTPS_PROXY": true, "NO_PROXY": true, "ALL_PROXY": true,
	"http_proxy": true, "https_proxy": true, "no_proxy": true, "all_proxy": true,
	"SSL_CERT_FILE": true, "SSL_CERT_DIR": true, "REQUESTS_CA_BUNDLE": true,
	"PLAYWRIGHT_BROWSERS_PATH": true,
	// Windows
	"SYSTEMROOT": true, "SYSTEMDRIVE": true, "WINDIR": true, "COMSPEC": true, "PATHEXT": true,
	"APPDATA": true, "LOCALAPPDATA": true, "USERPROFILE": true, "PROGRAMDATA": true,
}

var prefixosPermitidos = []string{"LC_", "ROBO_", "UV_", "PIP_", "POETRY_", "PDM_", "PIPENV_"}

// Mesmo com o prefixo permitido, estas descrevem o ambiente do agente: um
// uv sync com o UV_PROJECT_ENVIRONMENT dele instalaria as dependências do
// robô no lugar errado.
var variaveisDoAmbienteAtual = map[string]bool{
	"UV_PROJECT_ENVIRONMENT": true, "POETRY_ACTIVE": true, "PIPENV_ACTIVE": true,
}

// VariavelPermitida diz se uma variável do agente pode passar para o robô.
func VariavelPermitida(nome string) bool {
	if variaveisDoAmbienteAtual[nome] {
		return false
	}
	if variaveisPermitidas[nome] {
		return true
	}
	for _, prefixo := range prefixosPermitidos {
		if strings.HasPrefix(nome, prefixo) {
			return true
		}
	}
	return false
}

// Programas diz qual executável usar para cada ferramenta.
type Programas struct {
	UV, Poetry, PDM, Pipenv, Python string
}

// Plano descreve como preparar e rodar um robô. Programa é o que precisa
// estar instalado (vazio quando o próprio Python basta); Preparo são os
// comandos que instalam as dependências; Python é o começo do comando
// que roda Python dentro do ambiente do robô ("poetry run python").
type Plano struct {
	Ferramenta Ferramenta
	Origem     string
	Pasta      string
	Programa   string
	Preparo    [][]string
	Python     []string
	Env        []string
}

// Comando devolve o comando que roda o script sem buffer de saída.
func (p Plano) Comando(script string) []string {
	return append(append([]string{}, p.Python...), "-u", script)
}

// Descricao é a linha de log que diz o que foi detectado.
func (p Plano) Descricao() string {
	if p.Ferramenta == Sistema {
		return Prefixo + " sem gerenciador de dependências; rodando com " + p.Python[0]
	}
	return Prefixo + " " + string(p.Ferramenta) + " (" + p.Origem + ")"
}

// Detectar descobre a ferramenta pelos arquivos da pasta do robô e
// devolve também o arquivo que a identificou.
func Detectar(pasta string) (Ferramenta, string) {
	for _, m := range marcadores {
		if arquivoExiste(filepath.Join(pasta, m.arquivo)) {
			return m.ferramenta, m.arquivo
		}
	}
	pyproject := filepath.Join(pasta, "pyproject.toml")
	if arquivoExiste(pyproject) {
		switch {
		case temSecao(pyproject, "tool.poetry"):
			return Poetry, "pyproject.toml [tool.poetry]"
		case temSecao(pyproject, "tool.pdm"):
			return PDM, "pyproject.toml [tool.pdm]"
		default:
			return UV, "pyproject.toml"
		}
	}
	if arquivoExiste(filepath.Join(pasta, "requirements.txt")) {
		return Pip, "requirements.txt"
	}
	return Sistema, ""
}

// NomeDoVenv dá a cada robô um nome de ambiente único a partir do
// caminho dele na pasta aprovada: "coleta/notas" vira
// "coleta__notas-<8 hex>", com os 8 primeiros caracteres do SHA-256 do
// caminho relativo (com "/"). Sem o sufixo, "coleta/notas" e uma pasta
// chamada "coleta__notas" dividiriam o mesmo ambiente. A própria pasta
// aprovada vira "_raiz". É o mesmo nome do worker.
func NomeDoVenv(pastaRobos, pastaDoRobo string) string {
	if real, err := filepath.EvalSymlinks(pastaRobos); err == nil {
		pastaRobos = real
	}
	nome, err := filepath.Rel(pastaRobos, pastaDoRobo)
	if err != nil || nome == "." {
		return "_raiz"
	}
	resumo := sha256.Sum256([]byte(filepath.ToSlash(nome)))
	return strings.ReplaceAll(nome, string(filepath.Separator), "__") +
		"-" + hex.EncodeToString(resumo[:])[:8]
}

// AmbienteLimpo monta o ambiente do robô com só o que VariavelPermitida
// aceita (o MAESTRO_TOKEN e a configuração do agente não chegam ao robô),
// tira do PATH a pasta bin do venv ativo e liga a saída do Python sem
// buffer.
func AmbienteLimpo(base []string) []string {
	venvAtivo := ""
	for _, v := range base {
		if valor, ok := strings.CutPrefix(v, "VIRTUAL_ENV="); ok {
			venvAtivo = filepath.Join(valor, "bin")
		}
	}
	resultado := make([]string, 0, len(base)+1)
	for _, v := range base {
		nome, valor, _ := strings.Cut(v, "=")
		if !VariavelPermitida(nome) {
			continue
		}
		if nome == "PATH" && venvAtivo != "" {
			var partes []string
			for _, parte := range filepath.SplitList(valor) {
				if strings.TrimRight(parte, "/") != venvAtivo {
					partes = append(partes, parte)
				}
			}
			v = "PATH=" + strings.Join(partes, string(os.PathListSeparator))
		}
		resultado = append(resultado, v)
	}
	return append(resultado, "PYTHONUNBUFFERED=1")
}

// Planejar monta o plano do robô. Com pastaVenvs, o ambiente de cada
// robô fica em pastaVenvs/<nome do robô>, cada ferramenta com a sua
// variável; o pdm, que não tem essa variável, usa a pasta de venvs dele,
// também fora da pasta do robô. Sem pastaVenvs, cada ferramenta usa o
// próprio padrão.
func Planejar(script string, p Programas, pastaRobos, pastaVenvs string) Plano {
	pasta := filepath.Dir(script)
	ferramenta, origem := Detectar(pasta)
	venv := ""
	if pastaVenvs != "" {
		venv = filepath.Join(pastaVenvs, NomeDoVenv(pastaRobos, pasta))
	}
	plano := Plano{Ferramenta: ferramenta, Origem: origem, Pasta: pasta}

	switch ferramenta {
	case UV:
		plano.Programa = p.UV
		plano.Preparo = [][]string{{p.UV, "sync"}}
		plano.Python = []string{p.UV, "run", "--no-sync", "python"}
		if venv != "" {
			plano.Env = []string{"UV_PROJECT_ENVIRONMENT=" + venv}
		}
	case Poetry:
		plano.Programa = p.Poetry
		plano.Preparo = [][]string{{p.Poetry, "install", "--no-root"}}
		plano.Python = []string{p.Poetry, "run", "python"}
		plano.Env = []string{"POETRY_NO_INTERACTION=1"}
		if venv != "" {
			plano.Env = append(plano.Env,
				"POETRY_VIRTUALENVS_IN_PROJECT=false", "POETRY_VIRTUALENVS_PATH="+venv)
		}
	case PDM:
		plano.Programa = p.PDM
		plano.Preparo = [][]string{{p.PDM, "install"}}
		plano.Python = []string{p.PDM, "run", "python"}
		plano.Env = []string{"PDM_NON_INTERACTIVE=1"}
		if venv != "" {
			plano.Env = append(plano.Env, "PDM_VENV_IN_PROJECT=false")
		}
	case Pipenv:
		sincronizar := "install"
		if arquivoExiste(filepath.Join(pasta, "Pipfile.lock")) {
			sincronizar = "sync"
		}
		plano.Programa = p.Pipenv
		plano.Preparo = [][]string{{p.Pipenv, sincronizar}}
		plano.Python = []string{p.Pipenv, "run", "python"}
		plano.Env = []string{"PIPENV_NOSPIN=1", "PIPENV_IGNORE_VIRTUALENVS=1"}
		if venv != "" {
			plano.Env = append(plano.Env, "WORKON_HOME="+venv)
		}
	case Pip:
		if venv == "" {
			venv = filepath.Join(pasta, ".venv")
		}
		pythonDoVenv := PythonDoVenv(venv)
		if !arquivoExiste(pythonDoVenv) {
			plano.Preparo = append(plano.Preparo, []string{p.Python, "-m", "venv", venv})
		}
		plano.Preparo = append(plano.Preparo, []string{pythonDoVenv, "-m", "pip", "install",
			"--disable-pip-version-check", "-r", "requirements.txt"})
		plano.Python = []string{pythonDoVenv}
	default:
		plano.Python = []string{p.Python}
	}
	return plano
}

// PythonDoVenv devolve o executável do Python dentro de um venv.
func PythonDoVenv(venv string) string {
	if filepath.Separator == '\\' {
		return filepath.Join(venv, "Scripts", "python.exe")
	}
	return filepath.Join(venv, "bin", "python")
}

func arquivoExiste(caminho string) bool {
	info, err := os.Stat(caminho)
	return err == nil && info.Mode().IsRegular()
}

// temSecao diz se o pyproject.toml tem a tabela secao ou uma subtabela
// dela ("[tool.poetry]" ou "[tool.poetry.dependencies]"). Basta olhar os
// cabeçalhos, sem um leitor de TOML completo.
func temSecao(pyproject, secao string) bool {
	arquivo, err := os.Open(pyproject)
	if err != nil {
		return false
	}
	defer arquivo.Close()
	leitor := bufio.NewScanner(arquivo)
	for leitor.Scan() {
		linha := strings.TrimSpace(leitor.Text())
		if strings.HasPrefix(linha, "["+secao+"]") || strings.HasPrefix(linha, "["+secao+".") {
			return true
		}
	}
	return false
}
