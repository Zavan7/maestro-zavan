//go:build !linux

package protecao

// ProtegerProcesso não faz nada fora do Linux: macOS e Windows não têm o
// /proc com o ambiente de cada processo aberto ao mesmo usuário.
func ProtegerProcesso() error { return nil }
