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

// prepararProcesso coloca o robô num grupo de processos próprio, cujo id
// é o pid dele: os filhos herdam o grupo, e um sinal ao grupo alcança
// todos. Com usuario, o robô roda com esse usuário e grupo, sem os
// grupos extras do agente.
func prepararProcesso(cmd *exec.Cmd, usuario *Usuario) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if usuario != nil {
		cmd.SysProcAttr.Credential = &syscall.Credential{
			Uid: usuario.UID, Gid: usuario.GID, Groups: []uint32{},
		}
	}
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
