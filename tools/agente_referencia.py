"""Agente de referência em Python, para testar o protocolo do agente.

Não é o agente de produção (que será em Go): é a versão mais curta que
segue o protocolo de ``docs/agente/protocolo.md``, para testar o lado do
Maestro de ponta a ponta e servir de modelo ao agente em Go. Usa o mesmo
executor do worker (``robots.executor``), que não depende do Django.

Como rodar, da raiz do projeto, com o Maestro (Daphne) no ar::

    export MAESTRO_URL=ws://localhost:8000/ws/agente/
    export MAESTRO_TOKEN=mae_...
    export AGENTE_PASTA_ROBOS=/caminho/dos/robos
    uv run python -m tools.agente_referencia

Cada robô roda no ambiente do próprio gerenciador de dependências (uv,
poetry, pdm, pipenv ou pip), detectado pela pasta dele, com a mesma
regra do worker e do agente em Go (``robots.ambiente``).

Limitação conhecida: se a conexão cair no meio de uma execução, as
mensagens daquele intervalo se perdem (não há fila para reenviar; o
agente em Go tem).

English:
    Python reference agent, to test the agent protocol.

    It is not the production agent (which will be in Go): it is the
    shortest version that follows the protocol in
    ``docs/agente/protocolo.md``, to test Maestro's side end to end and
    serve as a model for the Go agent. It uses the same executor as the
    worker (``robots.executor``), which does not depend on Django.

    How to run, from the project root, with Maestro (Daphne) up::

        export MAESTRO_URL=ws://localhost:8000/ws/agente/
        export MAESTRO_TOKEN=mae_...
        export AGENTE_PASTA_ROBOS=/path/to/robots
        uv run python -m tools.agente_referencia

    Each robot runs in its own dependency manager's environment (uv,
    poetry, pdm, pipenv or pip), detected from its folder, with the same
    rule as the worker and the Go agent (``robots.ambiente``).

    Known limitation: if the connection drops mid-execution, the messages
    of that interval are lost (there is no queue to resend them; the Go
    agent has one).
"""

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import ClientConnection, connect

from robots.ambiente import Programas, rodar_robo
from robots.executor import Motivo

INTERVALO_HEARTBEAT_SEGUNDOS = 30
INTERVALO_LOTE_SEGUNDOS = 0.5
ESPERA_MAXIMA_RECONEXAO_SEGUNDOS = 30

logger = logging.getLogger("agente")


class Agente:
    """Uma conexão com o Maestro e as execuções que ela está rodando.

    English:
        A connection to Maestro and the executions it is running.
    """

    def __init__(
        self,
        url: str,
        token: str,
        pasta_robos: Path,
        pasta_venvs: Path | None = None,
    ) -> None:
        """Guarda a configuração do agente.

        Args:
            url: endereço do WebSocket, como ``ws://host/ws/agente/``.
            token: token gerado na aba de configurações.
            pasta_robos: pasta aprovada; só scripts dentro dela rodam.
            pasta_venvs: onde guardar o ambiente de cada robô, se não na
                pasta dele.

        English:
            Stores the agent configuration.

            Args:
                url: WebSocket address, such as ``ws://host/ws/agente/``.
                token: token generated in the settings tab.
                pasta_robos: approved folder; only scripts inside it run.
                pasta_venvs: where to keep each robot's environment, if
                    not in its folder.
        """
        self.url = url
        self.token = token
        self.pasta_robos = pasta_robos.resolve()
        self.pasta_venvs = pasta_venvs
        self.paradas: set[int] = set()

    def rodar_para_sempre(self) -> None:
        """Conecta e reconecta, esperando cada vez mais entre tentativas.

        Token recusado (403 no aperto de mão) encerra o agente: tentar de
        novo não resolve.

        English:
            Connects and reconnects, waiting longer between attempts.

            A refused token (403 on the handshake) stops the agent: trying
            again does not help.
        """
        espera = 1
        while True:
            try:
                self._conversar()
                espera = 1
            except InvalidStatus as erro:
                logger.error("Maestro recusou a conexão: %s", erro)
                return
            except (OSError, ConnectionClosed) as erro:
                logger.warning(
                    "Sem conexão (%s); de novo em %ss", erro, espera
                )
            time.sleep(espera)
            espera = min(espera * 2, ESPERA_MAXIMA_RECONEXAO_SEGUNDOS)

    def _conversar(self) -> None:
        """Abre a conexão, liga o heartbeat e atende os comandos.

        English:
            Opens the connection, starts the heartbeat and handles the
            commands.
        """
        cabecalhos = {"Authorization": f"Bearer {self.token}"}
        with connect(self.url, additional_headers=cabecalhos) as conexao:
            logger.info("Conectado a %s", self.url)
            threading.Thread(
                target=self._heartbeat, args=(conexao,), daemon=True
            ).start()
            for bruta in conexao:
                self._atender(conexao, json.loads(bruta))

    def _heartbeat(self, conexao: ClientConnection) -> None:
        """Avisa o Maestro a cada 30 segundos que o agente está vivo.

        Args:
            conexao: conexão aberta com o Maestro.

        English:
            Tells Maestro every 30 seconds that the agent is alive.

            Args:
                conexao: open connection to Maestro.
        """
        while True:
            time.sleep(INTERVALO_HEARTBEAT_SEGUNDOS)
            try:
                _enviar(conexao, {"tipo": "heartbeat"})
            except ConnectionClosed:
                return

    def _atender(self, conexao: ClientConnection, mensagem: object) -> None:
        """Trata um comando do Maestro.

        Args:
            conexao: conexão aberta com o Maestro.
            mensagem: mensagem recebida, já convertida de JSON.

        English:
            Handles a command from Maestro.

            Args:
                conexao: open connection to Maestro.
                mensagem: received message, already parsed from JSON.
        """
        if not isinstance(mensagem, dict):
            logger.warning("Mensagem fora do formato: %s", mensagem)
            return
        tipo = mensagem.get("tipo")
        if tipo == "iniciar":
            threading.Thread(
                target=self._executar, args=(conexao, mensagem), daemon=True
            ).start()
        elif tipo == "parar":
            self.paradas.add(mensagem["execucao_id"])
        elif tipo == "erro":
            logger.error("Maestro apontou erro: %s", mensagem.get("mensagem"))
        else:
            logger.warning("Mensagem desconhecida: %s", mensagem)

    def _executar(
        self, conexao: ClientConnection, comando: dict[str, Any]
    ) -> None:
        """Roda o robô pedido, mandando iniciado, log em lotes e fim.

        Args:
            conexao: conexão aberta com o Maestro.
            comando: mensagem ``iniciar``.

        English:
            Runs the requested robot, sending iniciado, batched log and
            fim.

            Args:
                conexao: open connection to Maestro.
                comando: ``iniciar`` message.
        """
        execucao_id = comando["execucao_id"]
        _enviar(conexao, {"tipo": "iniciado", "execucao_id": execucao_id})
        lote: list[str] = []
        ultimo_envio = [0.0]

        def enviar_lote(forcar: bool = False) -> None:
            agora = time.monotonic()
            if lote and (
                forcar or agora - ultimo_envio[0] >= INTERVALO_LOTE_SEGUNDOS
            ):
                _enviar(
                    conexao,
                    {
                        "tipo": "log",
                        "execucao_id": execucao_id,
                        "linhas": lote[:],
                    },
                )
                lote.clear()
                ultimo_envio[0] = agora

        try:
            script = resolver_robo(self.pasta_robos, comando["robo"])
        except (ValueError, FileNotFoundError) as erro:
            lote.append(str(erro))
            enviar_lote(forcar=True)
            _enviar_fim(conexao, execucao_id, Motivo.SCRIPT_INVALIDO, None)
            return

        motivo, codigo_saida = rodar_robo(
            script,
            programas=Programas(),
            pasta_robos=self.pasta_robos,
            pasta_venvs=self.pasta_venvs,
            timeout_segundos=comando["timeout_segundos"],
            deve_parar=lambda: execucao_id in self.paradas,
            ao_receber_linha=lote.append,
            a_cada_volta=enviar_lote,
            venv_atual=sys.prefix if sys.prefix != sys.base_prefix else None,
        )
        enviar_lote(forcar=True)
        _enviar_fim(conexao, execucao_id, motivo, codigo_saida)
        self.paradas.discard(execucao_id)


def resolver_robo(pasta: Path, robo: str) -> Path:
    """Resolve o robô dentro da pasta aprovada, como o worker faz.

    O Maestro manda só o identificador do robô; o agente decide o que
    executar, e nunca sai da própria pasta.

    Args:
        pasta: pasta aprovada do agente.
        robo: identificador recebido no ``iniciar``.

    Returns:
        Caminho absoluto do script.

    Raises:
        ValueError: se o caminho sai da pasta aprovada.
        FileNotFoundError: se o script não existe.

    English:
        Resolves the robot inside the approved folder, like the worker.

        Maestro sends only the robot identifier; the agent decides what to
        run, and never leaves its own folder.

        Args:
            pasta: the agent's approved folder.
            robo: identifier received in ``iniciar``.

        Returns:
            Absolute path to the script.

        Raises:
            ValueError: if the path leaves the approved folder.
            FileNotFoundError: if the script does not exist.
    """
    script = (pasta / robo).resolve()
    if not script.is_relative_to(pasta):
        raise ValueError("Script fora do diretório permitido.")
    if not script.is_file():
        raise FileNotFoundError(f"Script não encontrado: {robo}")
    return script


def _enviar(conexao: ClientConnection, mensagem: dict[str, Any]) -> None:
    """Envia uma mensagem JSON ao Maestro.

    O envio do ``websockets`` é seguro entre threads: o heartbeat e cada
    execução enviam pela mesma conexão.

    Args:
        conexao: conexão aberta com o Maestro.
        mensagem: mensagem do protocolo.

    English:
        Sends a JSON message to Maestro.

        ``websockets`` sending is thread-safe: the heartbeat and each
        execution send through the same connection.

        Args:
            conexao: open connection to Maestro.
            mensagem: protocol message.
    """
    conexao.send(json.dumps(mensagem, ensure_ascii=False))


def _enviar_fim(
    conexao: ClientConnection,
    execucao_id: int,
    motivo: Motivo,
    codigo_saida: int | None,
) -> None:
    """Envia a mensagem ``fim`` com o motivo e o código de saída.

    Args:
        conexao: conexão aberta com o Maestro.
        execucao_id: id da execução.
        motivo: por que a execução terminou.
        codigo_saida: código de saída, se o processo chegou a rodar.

    English:
        Sends the ``fim`` message with the reason and the exit code.

        Args:
            conexao: open connection to Maestro.
            execucao_id: execution id.
            motivo: why the execution ended.
            codigo_saida: exit code, if the process got to run.
    """
    _enviar(
        conexao,
        {
            "tipo": "fim",
            "execucao_id": execucao_id,
            "motivo": motivo.value,
            "codigo_saida": codigo_saida,
        },
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    Agente(
        url=os.environ["MAESTRO_URL"],
        token=os.environ["MAESTRO_TOKEN"],
        pasta_robos=Path(os.environ["AGENTE_PASTA_ROBOS"]),
        pasta_venvs=(
            Path(os.environ["AGENTE_PASTA_VENVS"])
            if os.getenv("AGENTE_PASTA_VENVS")
            else None
        ),
    ).rodar_para_sempre()
