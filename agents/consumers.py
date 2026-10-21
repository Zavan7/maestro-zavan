"""Consumer do WebSocket por onde os agentes falam com o Maestro.

English:
    WebSocket consumer through which agents talk to Maestro.
"""

import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from agents import protocolo
from agents.comandos import grupo_do_agente
from agents.protocolo import MensagemInvalida

logger = logging.getLogger(__name__)

FECHAMENTO_SEM_TOKEN = 4401
FECHAMENTO_SUBSTITUIDO = 4409


def token_do_cabecalho(
    cabecalhos: Iterable[tuple[bytes, bytes]],
) -> str | None:
    """Lê o token do cabeçalho ``Authorization: Bearer <token>``.

    O token vai no cabeçalho, e não na URL, para não aparecer em logs de
    servidor e de proxy.

    Args:
        cabecalhos: cabeçalhos da conexão, como pares de bytes.

    Returns:
        O token, ou ``None`` se o cabeçalho falta ou está fora do formato.

    English:
        Reads the token from the ``Authorization: Bearer <token>`` header.

        The token goes in the header, not in the URL, so it does not show
        up in server and proxy logs.

        Args:
            cabecalhos: connection headers, as byte pairs.

        Returns:
            The token, or ``None`` if the header is missing or malformed.
    """
    for nome, valor in cabecalhos:
        if nome.lower() == b"authorization":
            tipo, _, token = valor.decode("latin-1").partition(" ")
            if tipo.lower() == "bearer" and token.strip():
                return token.strip()
    return None


class AgenteConsumer(AsyncJsonWebsocketConsumer):
    """Conexão de um agente: recebe status e log, entrega comandos.

    - **Autenticação**: o token vem no cabeçalho ``Authorization``; sem
      token válido de agente ativo, a conexão é recusada (4401). Não usa a
      sessão do Django: o agente não é um usuário.
    - **Uma conexão por agente**: ao conectar, avisa o grupo do agente
      antes de entrar nele; uma conexão anterior que ainda esteja aberta
      fecha com 4409. Sem isso, um agente reiniciado receberia cada
      comando duas vezes.
    - **Mensagens do agente**: cada ``tipo`` tem um tratador em
      ``agents.protocolo``; mensagem inválida ou de tipo desconhecido
      volta como ``{"tipo": "erro", "mensagem": "..."}``, sem derrubar a
      conexão.
    - **Comandos do Maestro**: chegam pelo grupo como ``agente.comando``
      e são repassados ao agente como estão.

    English:
        An agent's connection: receives status and log, delivers commands.

        - **Authentication**: the token comes in the ``Authorization``
          header; without a valid token of an active agent, the connection
          is refused (4401). It does not use the Django session: the agent
          is not a user.
        - **One connection per agent**: on connect, it notifies the
          agent's group before joining it; an earlier connection still
          open closes with 4409. Otherwise, a restarted agent would get
          every command twice.
        - **Agent messages**: each ``tipo`` has a handler in
          ``agents.protocolo``; an invalid message or unknown type comes
          back as ``{"tipo": "erro", "mensagem": "..."}``, without
          dropping the connection.
        - **Maestro commands**: arrive through the group as
          ``agente.comando`` and are relayed to the agent as is.
    """

    agente_id: int | None = None
    grupo: str | None = None

    async def connect(self) -> None:
        """Autentica o agente, assume o grupo dele e registra o sinal.

        English:
            Authenticates the agent, takes over its group and records the
            signal.
        """
        token = token_do_cabecalho(self.scope.get("headers", []))
        agente = (
            await database_sync_to_async(protocolo.autenticar)(token)
            if token
            else None
        )
        if agente is None:
            await self.close(code=FECHAMENTO_SEM_TOKEN)
            return

        self.agente_id = agente.pk
        self.grupo = grupo_do_agente(agente.pk)
        await self.channel_layer.group_send(
            self.grupo, {"type": "agente.substituido"}
        )
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()
        await database_sync_to_async(protocolo.registrar_sinal)(agente.pk)
        logger.info("Agente %s conectado.", agente.nome)

    async def disconnect(self, code: int) -> None:
        """Sai do grupo do agente ao fechar a conexão.

        Args:
            code: código de fechamento do WebSocket.

        English:
            Leaves the agent's group when the connection closes.

            Args:
                code: WebSocket close code.
        """
        if self.grupo is not None:
            await self.channel_layer.group_discard(
                self.grupo, self.channel_name
            )

    async def receive_json(self, content: object, **kwargs: Any) -> None:
        """Valida a mensagem do agente e chama o tratador do tipo dela.

        Args:
            content: mensagem recebida, já convertida de JSON.
            **kwargs: argumentos extras do Channels, não usados.

        English:
            Validates the agent's message and calls the handler for its
            type.

            Args:
                content: received message, already parsed from JSON.
                **kwargs: extra Channels arguments, unused.
        """
        assert self.agente_id is not None  # só recebe depois do connect
        tratadores: dict[
            str, Callable[[int, dict[str, Any]], Awaitable[None]]
        ] = {
            "heartbeat": self._heartbeat,
            "iniciado": self._iniciado,
            "log": self._log,
            "fim": self._fim,
        }
        tipo = content.get("tipo") if isinstance(content, dict) else None
        tratador = tratadores.get(tipo) if isinstance(tipo, str) else None
        if tratador is None or not isinstance(content, dict):
            await self._erro(f"tipo de mensagem desconhecido: {tipo!r}")
            return
        try:
            await tratador(self.agente_id, content)
        except MensagemInvalida as erro:
            await self._erro(str(erro))

    async def agente_comando(self, evento: dict[str, Any]) -> None:
        """Repassa ao agente um comando enviado ao grupo.

        Args:
            evento: evento do grupo, com a ``mensagem`` do protocolo.

        English:
            Relays to the agent a command sent to the group.

            Args:
                evento: group event, with the protocol ``mensagem``.
        """
        await self.send_json(evento["mensagem"])

    async def agente_substituido(self, evento: dict[str, Any]) -> None:
        """Fecha esta conexão porque o agente conectou de novo.

        Args:
            evento: evento do grupo, sem dados.

        English:
            Closes this connection because the agent connected again.

            Args:
                evento: group event, with no data.
        """
        await self.close(code=FECHAMENTO_SUBSTITUIDO)

    async def agente_desconectar(self, evento: dict[str, Any]) -> None:
        """Fecha esta conexão porque o token mudou ou o agente foi desativado.

        Args:
            evento: evento do grupo, sem dados.

        English:
            Closes this connection because the token changed or the agent
            was deactivated.

            Args:
                evento: group event, with no data.
        """
        await self.close(code=FECHAMENTO_SEM_TOKEN)

    async def _heartbeat(
        self, agente_id: int, mensagem: dict[str, Any]
    ) -> None:
        """Registra o sinal de vida do agente.

        Args:
            agente_id: id do agente.
            mensagem: mensagem ``heartbeat``, sem outros campos.

        English:
            Records the agent's sign of life.

            Args:
                agente_id: agent id.
                mensagem: ``heartbeat`` message, with no other fields.
        """
        await database_sync_to_async(protocolo.registrar_sinal)(agente_id)

    async def _iniciado(
        self, agente_id: int, mensagem: dict[str, Any]
    ) -> None:
        """Reivindica a execução; se ela foi cancelada, manda parar.

        Args:
            agente_id: id do agente.
            mensagem: mensagem ``iniciado`` com ``execucao_id``.

        English:
            Claims the execution; if it was cancelled, says to stop.

            Args:
                agente_id: agent id.
                mensagem: ``iniciado`` message with ``execucao_id``.
        """
        execucao_id = protocolo.ler_inteiro(mensagem, "execucao_id")
        reivindicada = await database_sync_to_async(
            protocolo.confirmar_inicio
        )(agente_id, execucao_id)
        if not reivindicada:
            await self.send_json({"tipo": "parar", "execucao_id": execucao_id})

    async def _log(self, agente_id: int, mensagem: dict[str, Any]) -> None:
        """Grava e repassa à tela um lote de linhas do log.

        Args:
            agente_id: id do agente.
            mensagem: mensagem ``log``.

        English:
            Saves and relays to the page a batch of log lines.

            Args:
                agente_id: agent id.
                mensagem: ``log`` message.
        """
        await database_sync_to_async(protocolo.receber_linhas)(
            agente_id, mensagem
        )

    async def _fim(self, agente_id: int, mensagem: dict[str, Any]) -> None:
        """Encerra a execução com o desfecho informado pelo agente.

        Args:
            agente_id: id do agente.
            mensagem: mensagem ``fim``.

        English:
            Ends the execution with the outcome reported by the agent.

            Args:
                agente_id: agent id.
                mensagem: ``fim`` message.
        """
        await database_sync_to_async(protocolo.receber_fim)(
            agente_id, mensagem
        )

    async def _erro(self, motivo: str) -> None:
        """Devolve ao agente uma mensagem de erro de protocolo.

        Args:
            motivo: o que estava errado na mensagem.

        English:
            Sends a protocol error message back to the agent.

            Args:
                motivo: what was wrong with the message.
        """
        logger.warning("Agente %s: %s", self.agente_id, motivo)
        await self.send_json({"tipo": "erro", "mensagem": motivo})
