"""Comandos que o Maestro envia a um agente pelo WebSocket.

Cada agente conectado está no grupo ``agente_<id>``; o ``AgenteConsumer``
repassa a mensagem do evento, como está, para a conexão do agente. O
agente nunca recebe caminho ou comando cru: só o identificador do robô,
que ele resolve dentro da própria pasta aprovada.

Mensagens:

- ``{"tipo": "iniciar", "execucao_id": 42, "robo": "coleta/main.py",
  "timeout_segundos": 300}``
- ``{"tipo": "parar", "execucao_id": 42}``

English:
    Commands Maestro sends to an agent over the WebSocket.

    Each connected agent is in the ``agente_<id>`` group;
    ``AgenteConsumer`` relays the event's message, as is, to the agent's
    connection. The agent never gets a raw path or command: only the
    robot identifier, which it resolves inside its own approved folder.

    Messages:

    - ``{"tipo": "iniciar", "execucao_id": 42, "robo": "coleta/main.py",
      "timeout_segundos": 300}``
    - ``{"tipo": "parar", "execucao_id": 42}``
"""

import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


def grupo_do_agente(agente_id: int) -> str:
    """Retorna o nome do grupo do Channels de um agente.

    Args:
        agente_id: id do agente.

    Returns:
        O nome do grupo, como ``agente_3``.

    English:
        Returns the Channels group name of an agent.

        Args:
            agente_id: agent id.

        Returns:
            The group name, such as ``agente_3``.
    """
    return f"agente_{agente_id}"


def mandar_iniciar(
    agente_id: int, execucao_id: int, robo: str, timeout_segundos: int
) -> bool:
    """Manda o agente iniciar uma execução.

    Args:
        agente_id: id do agente que roda o robô.
        execucao_id: id da execução pendente.
        robo: identificador do robô dentro da pasta aprovada do agente.
        timeout_segundos: tempo máximo da execução.

    Returns:
        ``True`` se o comando saiu; ``False`` se o canal não respondeu.

    English:
        Tells the agent to start an execution.

        Args:
            agente_id: id of the agent that runs the robot.
            execucao_id: id of the pending execution.
            robo: robot identifier inside the agent's approved folder.
            timeout_segundos: maximum execution time.

        Returns:
            ``True`` if the command went out; ``False`` if the channel did
            not answer.
    """
    return _mandar(
        agente_id,
        {
            "tipo": "iniciar",
            "execucao_id": execucao_id,
            "robo": robo,
            "timeout_segundos": timeout_segundos,
        },
    )


def mandar_parar(agente_id: int, execucao_id: int) -> bool:
    """Manda o agente parar uma execução.

    Args:
        agente_id: id do agente que roda o robô.
        execucao_id: id da execução.

    Returns:
        ``True`` se o comando saiu; ``False`` se o canal não respondeu.

    English:
        Tells the agent to stop an execution.

        Args:
            agente_id: id of the agent that runs the robot.
            execucao_id: execution id.

        Returns:
            ``True`` if the command went out; ``False`` if the channel did
            not answer.
    """
    return _mandar(agente_id, {"tipo": "parar", "execucao_id": execucao_id})


def desconectar(agente_id: int) -> bool:
    """Fecha a conexão aberta do agente, se houver.

    Usado quando o token muda ou o agente é desativado: uma conexão já
    aberta não pode continuar valendo com uma credencial que deixou de
    valer.

    Args:
        agente_id: id do agente.

    Returns:
        ``True`` se o aviso saiu; ``False`` se o canal não respondeu.

    English:
        Closes the agent's open connection, if any.

        Used when the token changes or the agent is deactivated: an open
        connection cannot stay valid with a credential that stopped being
        valid.

        Args:
            agente_id: agent id.

        Returns:
            ``True`` if the notice went out; ``False`` if the channel did
            not answer.
    """
    return _enviar(agente_id, {"type": "agente.desconectar"})


def _mandar(agente_id: int, mensagem: dict[str, Any]) -> bool:
    """Envia ao agente uma mensagem do protocolo.

    Args:
        agente_id: id do agente.
        mensagem: mensagem do protocolo, entregue ao agente como está.

    Returns:
        ``True`` se o envio deu certo; ``False`` caso contrário.

    English:
        Sends a protocol message to the agent.

        Args:
            agente_id: agent id.
            mensagem: protocol message, delivered to the agent as is.

        Returns:
            ``True`` if sending worked; ``False`` otherwise.
    """
    return _enviar(agente_id, {"type": "agente.comando", "mensagem": mensagem})


def _enviar(agente_id: int, evento: dict[str, Any]) -> bool:
    """Envia ``evento`` ao grupo do agente, sem deixar o erro subir.

    Args:
        agente_id: id do agente.
        evento: evento do Channels, com o campo ``type``.

    Returns:
        ``True`` se o envio deu certo; ``False`` caso contrário.

    English:
        Sends ``evento`` to the agent's group, without letting the error
        escape.

        Args:
            agente_id: agent id.
            evento: Channels event, with the ``type`` field.

        Returns:
            ``True`` if sending worked; ``False`` otherwise.
    """
    camada = get_channel_layer()
    if camada is None:
        return False
    try:
        async_to_sync(camada.group_send)(grupo_do_agente(agente_id), evento)
    except (OSError, RedisError) as erro:
        logger.warning("Aviso ao agente %s não saiu: %s", agente_id, erro)
        return False
    return True
