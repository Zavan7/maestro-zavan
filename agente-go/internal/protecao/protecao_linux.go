//go:build linux

// Package protecao fecha o processo do agente para outros processos do
// mesmo usuário.
package protecao

import "syscall"

// prSetDumpable é a operação PR_SET_DUMPABLE do prctl (linux/prctl.h).
const prSetDumpable = 4

// ProtegerProcesso impede que outros processos do mesmo usuário leiam
// este. Um robô roda com o mesmo usuário do agente, e por padrão o Linux
// deixa um processo ler o /proc/<pid>/environ de outro do mesmo usuário:
// foi assim que um robô de teste leu o MAESTRO_TOKEN do agente, mesmo
// com a variável fora do ambiente dele. prctl(PR_SET_DUMPABLE, 0) passa o
// /proc do agente para o root e impede que alguém do mesmo usuário o
// depure. O robô, iniciado com exec, volta ao normal.
func ProtegerProcesso() error {
	_, _, errno := syscall.RawSyscall(syscall.SYS_PRCTL, prSetDumpable, 0, 0)
	if errno != 0 {
		return errno
	}
	return nil
}
