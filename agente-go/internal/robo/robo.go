// Package robo decide o que executar a partir do identificador que o
// Maestro manda, sem nunca sair da pasta aprovada do agente.
package robo

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ErrForaDaPasta indica um identificador que aponta para fora da pasta
// aprovada (../, caminho absoluto ou link simbólico para fora).
var ErrForaDaPasta = errors.New("script fora do diretório permitido")

// ErrNaoEncontrado indica que o script não existe ou não é um arquivo.
var ErrNaoEncontrado = errors.New("script não encontrado")

// Resolver devolve o caminho absoluto do script do robô, dentro da pasta
// aprovada. É a mesma regra do worker (_resolver_script) e da referência
// em Python: (pasta / robo).resolve() precisa continuar dentro da pasta.
func Resolver(pasta, robo string) (string, error) {
	if strings.TrimSpace(robo) == "" {
		return "", fmt.Errorf("%w: identificador vazio", ErrNaoEncontrado)
	}
	if filepath.IsAbs(robo) {
		return "", fmt.Errorf("%w: %q", ErrForaDaPasta, robo)
	}
	pastaReal, err := filepath.EvalSymlinks(pasta)
	if err != nil {
		return "", fmt.Errorf("pasta aprovada inacessível: %w", err)
	}

	// Primeiro a conferência pelo texto, que barra "../" mesmo quando o
	// destino não existe; depois a do caminho real, que barra links
	// simbólicos que apontam para fora.
	candidato := filepath.Join(pastaReal, robo)
	if !dentro(pastaReal, candidato) {
		return "", fmt.Errorf("%w: %q", ErrForaDaPasta, robo)
	}
	real, err := filepath.EvalSymlinks(candidato)
	if err != nil {
		return "", fmt.Errorf("%w: %s", ErrNaoEncontrado, robo)
	}
	if !dentro(pastaReal, real) {
		return "", fmt.Errorf("%w: %q", ErrForaDaPasta, robo)
	}
	info, err := os.Stat(real)
	if err != nil || !info.Mode().IsRegular() {
		return "", fmt.Errorf("%w: %s", ErrNaoEncontrado, robo)
	}
	return real, nil
}

// Comando monta o programa, os argumentos e a pasta de trabalho para
// rodar o script. Se a pasta do script tem pyproject.toml, o robô roda
// com "uv run", nas dependências dele; senão, com o Python informado.
// Sempre com -u, para cada linha do log sair assim que é escrita.
func Comando(script, uv, python string) (programa string, args []string, pasta string) {
	pasta = filepath.Dir(script)
	if _, err := os.Stat(filepath.Join(pasta, "pyproject.toml")); err == nil {
		return uv, []string{"run", "python", "-u", filepath.Base(script)}, pasta
	}
	return python, []string{"-u", script}, pasta
}

// dentro diz se caminho é a própria pasta ou está abaixo dela.
func dentro(pasta, caminho string) bool {
	rel, err := filepath.Rel(pasta, caminho)
	if err != nil {
		return false
	}
	return rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) &&
		!filepath.IsAbs(rel)
}
