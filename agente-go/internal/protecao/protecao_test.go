package protecao

import (
	"os"
	"os/exec"
	"runtime"
	"strings"
	"testing"
)

// O teste roda num processo filho, porque a proteção vale para o
// processo inteiro e não pode ser desfeita.
func TestFilhoNaoLeOAmbienteDoProcessoProtegido(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("só no Linux")
	}
	if os.Getenv("PROTECAO_FILHO") == "1" {
		if err := ProtegerProcesso(); err != nil {
			t.Fatal(err)
		}
		saida, _ := exec.Command("cat", "/proc/"+itoa(os.Getpid())+"/environ").CombinedOutput()
		if strings.Contains(string(saida), "SEGREDO_DO_TESTE=") {
			t.Fatalf("o filho leu o ambiente protegido: %q", saida)
		}
		return
	}
	if os.Geteuid() == 0 {
		t.Skip("o root lê o /proc de qualquer processo; rode como usuário comum")
	}
	cmd := exec.Command(os.Args[0], "-test.run", "^TestFilhoNaoLeOAmbienteDoProcessoProtegido$")
	cmd.Env = append(os.Environ(), "PROTECAO_FILHO=1", "SEGREDO_DO_TESTE=mae_x")
	if saida, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("%v\n%s", err, saida)
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for ; n > 0; n /= 10 {
		b = append([]byte{byte('0' + n%10)}, b...)
	}
	return string(b)
}
