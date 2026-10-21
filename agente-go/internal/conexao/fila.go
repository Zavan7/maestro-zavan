package conexao

import (
	"sync"

	"github.com/Zavan7/maestro-zavan/agente-go/internal/protocolo"
)

// LimiteFila é quantas mensagens a fila de saída guarda enquanto o
// agente está sem conexão. Acima disso, novas mensagens "log" são
// descartadas; "iniciado" e "fim" nunca são, porque sem elas o Maestro
// não sabe como a execução terminou.
const LimiteFila = 10000

// fila guarda as mensagens que ainda não saíram. Ela sobrevive às
// quedas de conexão: o que não foi enviado sai depois de reconectar, na
// mesma ordem. Uma mensagem só sai da fila depois de escrita com
// sucesso, então nada que já saiu é reenviado.
type fila struct {
	mu     sync.Mutex
	itens  []any
	limite int
	aviso  chan struct{}
}

func novaFila(limite int) *fila {
	return &fila{limite: limite, aviso: make(chan struct{}, 1)}
}

// por acrescenta uma mensagem e acorda quem escreve. Devolve false se a
// mensagem foi descartada por a fila estar cheia.
func (f *fila) por(v any) bool {
	f.mu.Lock()
	if _, ehLog := v.(protocolo.Log); ehLog && len(f.itens) >= f.limite {
		f.mu.Unlock()
		return false
	}
	f.itens = append(f.itens, v)
	f.mu.Unlock()
	select {
	case f.aviso <- struct{}{}:
	default:
	}
	return true
}

// primeiro devolve a próxima mensagem sem tirá-la da fila.
func (f *fila) primeiro() (any, bool) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.itens) == 0 {
		return nil, false
	}
	return f.itens[0], true
}

// tirar remove a primeira mensagem, depois que ela foi enviada.
func (f *fila) tirar() {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.itens) > 0 {
		f.itens[0] = nil
		f.itens = f.itens[1:]
	}
}

// tamanho diz quantas mensagens esperam envio.
func (f *fila) tamanho() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return len(f.itens)
}
