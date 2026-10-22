package robo

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

// criar escreve um arquivo (e as pastas dele) com conteúdo qualquer.
func criar(t *testing.T, caminho string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(caminho), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(caminho, []byte("print('oi')\n"), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestResolverAceitaScriptDentroDaPasta(t *testing.T) {
	pasta := t.TempDir()
	criar(t, filepath.Join(pasta, "coleta", "main.py"))

	script, err := Resolver(pasta, "coleta/main.py")
	if err != nil {
		t.Fatalf("erro inesperado: %v", err)
	}
	real, _ := filepath.EvalSymlinks(filepath.Join(pasta, "coleta", "main.py"))
	if script != real {
		t.Errorf("script = %q, esperado %q", script, real)
	}
}

func TestResolverRecusaFugasDaPasta(t *testing.T) {
	raiz := t.TempDir()
	pasta := filepath.Join(raiz, "robos")
	criar(t, filepath.Join(pasta, "ok.py"))
	fora := filepath.Join(raiz, "segredo.py")
	criar(t, fora)
	if err := os.Symlink(fora, filepath.Join(pasta, "atalho.py")); err != nil {
		t.Fatal(err)
	}

	casos := map[string]string{
		"pai":             "../segredo.py",
		"pai escondido":   "sub/../../segredo.py",
		"absoluto":        fora,
		"link para fora":  "atalho.py",
		"pai inexistente": "../nao_existe.py",
	}
	for nome, robo := range casos {
		t.Run(nome, func(t *testing.T) {
			_, err := Resolver(pasta, robo)
			if !errors.Is(err, ErrForaDaPasta) {
				t.Errorf("Resolver(%q) = %v, esperado ErrForaDaPasta", robo, err)
			}
		})
	}
}

func TestResolverRecusaScriptInexistenteOuPasta(t *testing.T) {
	pasta := t.TempDir()
	if err := os.Mkdir(filepath.Join(pasta, "sou_pasta"), 0o755); err != nil {
		t.Fatal(err)
	}
	for _, robo := range []string{"nao_existe.py", "sou_pasta", "", "  "} {
		if _, err := Resolver(pasta, robo); !errors.Is(err, ErrNaoEncontrado) {
			t.Errorf("Resolver(%q) = %v, esperado ErrNaoEncontrado", robo, err)
		}
	}
}
