//go:build !unix

package executor

import (
	"os"
	"os/exec"
)

// Fora do Unix ainda não há grupo de processos: o encerramento alcança
// só o processo principal. No Windows, o caminho é um Job Object.
type sinal int

const (
	sinalEducado sinal = iota
	sinalForcado
)

func prepararGrupo(*exec.Cmd) {}

func sinalizarGrupo(cmd *exec.Cmd, _ sinal) {
	if cmd.Process != nil {
		_ = cmd.Process.Kill()
	}
}

func codigoSaida(estado *os.ProcessState) int {
	if estado == nil {
		return -1
	}
	return estado.ExitCode()
}
