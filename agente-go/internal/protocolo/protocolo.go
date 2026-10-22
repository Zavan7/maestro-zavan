// Package protocolo define as mensagens trocadas com o Maestro, como
// descrito em docs/agente/protocolo.md.
package protocolo

// Limites de uma mensagem "log", conferidos pelo Maestro.
const (
	MaxLinhasPorMensagem  = 1000
	MaxCaracteresPorLinha = 10000
)

// Motivo diz por que uma execução terminou. Os valores são os mesmos do
// Motivo do executor em Python (robots/executor.py).
type Motivo string

const (
	Concluido      Motivo = "concluido"
	TempoEsgotado  Motivo = "tempo_esgotado"
	Parado         Motivo = "parado"
	ScriptInvalido Motivo = "script_invalido"
	// AmbienteInvalido: a ferramenta de dependências do robô (uv, poetry,
	// pdm, pipenv) não está instalada; o Maestro não tenta de novo.
	AmbienteInvalido Motivo = "ambiente_invalido"
	// PreparoFalhou: instalar as dependências falhou ou passou do tempo;
	// o Maestro pode tentar de novo.
	PreparoFalhou Motivo = "preparo_falhou"
)

// Recebida guarda os campos que o agente lê dos comandos do Maestro.
type Recebida struct {
	Tipo            string `json:"tipo"`
	ExecucaoID      int64  `json:"execucao_id"`
	Robo            string `json:"robo"`
	TimeoutSegundos int    `json:"timeout_segundos"`
	Mensagem        string `json:"mensagem"`
}

// Heartbeat avisa que o agente está vivo.
type Heartbeat struct {
	Tipo string `json:"tipo"`
}

// NovoHeartbeat monta a mensagem "heartbeat".
func NovoHeartbeat() Heartbeat { return Heartbeat{Tipo: "heartbeat"} }

// Iniciado confirma que o agente recebeu o "iniciar" e vai rodar.
type Iniciado struct {
	Tipo       string `json:"tipo"`
	ExecucaoID int64  `json:"execucao_id"`
}

// NovoIniciado monta a mensagem "iniciado".
func NovoIniciado(execucaoID int64) Iniciado {
	return Iniciado{Tipo: "iniciado", ExecucaoID: execucaoID}
}

// Log leva um lote de linhas da saída do robô.
type Log struct {
	Tipo       string   `json:"tipo"`
	ExecucaoID int64    `json:"execucao_id"`
	Linhas     []string `json:"linhas"`
}

// NovoLog monta a mensagem "log".
func NovoLog(execucaoID int64, linhas []string) Log {
	return Log{Tipo: "log", ExecucaoID: execucaoID, Linhas: linhas}
}

// Fim informa como a execução terminou. CodigoSaida é nil (null no JSON)
// quando o processo nem chegou a rodar.
type Fim struct {
	Tipo        string `json:"tipo"`
	ExecucaoID  int64  `json:"execucao_id"`
	Motivo      Motivo `json:"motivo"`
	CodigoSaida *int   `json:"codigo_saida"`
}

// NovoFim monta a mensagem "fim".
func NovoFim(execucaoID int64, motivo Motivo, codigoSaida *int) Fim {
	return Fim{
		Tipo:        "fim",
		ExecucaoID:  execucaoID,
		Motivo:      motivo,
		CodigoSaida: codigoSaida,
	}
}
