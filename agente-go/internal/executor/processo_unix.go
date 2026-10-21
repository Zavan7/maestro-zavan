//go:build unix

package executor

import (
	"os"
	"os/exec"
	"syscall"
)

var (
	sinalEducado = syscall.SIGTERM
	sinalForcado = syscall.SIGKILL
)

// prepararGrupo coloca o robô num grupo de processos próprio, cujo id é
// o pid dele. Os filhos herdam o grupo, e um sinal ao grupo alcança
// todos.
func prepararGrupo(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

// sinalizarGrupo manda o sinal ao grupo inteiro. Se ninguém do grupo
// existe mais, não há o que fazer.
func sinalizarGrupo(cmd *exec.Cmd, sinal syscall.Signal) {
	if cmd.Process == nil {
		return
	}
	_ = syscall.Kill(-cmd.Process.Pid, sinal)
}

// codigoSaida devolve o código de saída, ou o sinal negativo quando o
// processo foi encerrado por sinal (como o subprocess do Python).
func codigoSaida(estado *os.ProcessState) int {
	if estado == nil {
		return -1
	}
	if status, ok := estado.Sys().(syscall.WaitStatus); ok && status.Signaled() {
		return -int(status.Signal())
	}
	return estado.ExitCode()
}
