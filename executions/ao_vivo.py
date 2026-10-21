"""Publicação do log ao vivo de uma execução pelo Django Channels.

Quem roda o robô (o worker do Celery hoje, o agente em Go depois) chama
estas funções; o ``ExecucaoConsumer`` repassa cada evento aos navegadores
abertos na tela de detalhe. Cada execução tem o seu grupo,
``execucao_<id>``.

Contrato das mensagens que chegam ao navegador:

- ``{"tipo": "linhas", "linhas": [{"numero": 12, "texto": "..."}]}``
- ``{"tipo": "fim", "status": "sucesso"}``

Publicar é um extra: se o Redis do Channels estiver fora, a execução
continua e o log completo fica no banco. Por isso as falhas de envio
viram um aviso no log, e nunca uma exceção para quem chamou.

English:
    Publishing an execution's live log through Django Channels.

    Whoever runs the robot (the Celery worker today, the Go agent later)
    calls these functions; ``ExecucaoConsumer`` relays each event to the
    browsers open on the detail page. Each execution has its own group,
    ``execucao_<id>``.

    Contract of the messages that reach the browser:

    - ``{"tipo": "linhas", "linhas": [{"numero": 12, "texto": "..."}]}``
    - ``{"tipo": "fim", "status": "sucesso"}``

    Publishing is an extra: if the Channels Redis is down, the execution
    goes on and the full log stays in the database. That is why send
    failures become a warning in the log, never an exception for the
    caller.
"""

import logging
from typing import Any, TypedDict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class LinhaDoLog(TypedDict):
    """Uma linha do log com o seu número desde o início da execução.

    English:
        A log line with its number since the start of the execution.
    """

    numero: int
    texto: str


def numerar_log(log: str, total_linhas: int) -> list[LinhaDoLog]:
    """Numera as linhas do log guardado, que pode ter perdido o começo.

    Só o fim do log cabe no limite, então a primeira linha guardada nem
    sempre é a de número 1: a numeração termina em ``total_linhas``. Para
    execuções antigas, sem ``total_linhas``, conta as próprias linhas.

    Args:
        log: texto do log guardado no banco.
        total_linhas: quantas linhas a execução produziu até agora.

    Returns:
        As linhas guardadas, cada uma com o seu número.

    English:
        Numbers the stored log lines, which may have lost the start.

        Only the end of the log fits in the limit, so the first stored line
        is not always number 1: the numbering ends at ``total_linhas``.
        For old executions, without ``total_linhas``, it counts the lines
        themselves.

        Args:
            log: log text stored in the database.
            total_linhas: how many lines the execution has produced so far.

        Returns:
            The stored lines, each with its number.
    """
    linhas = log.splitlines()
    primeira = max(total_linhas, len(linhas)) - len(linhas) + 1
    return [
        LinhaDoLog(numero=primeira + indice, texto=texto)
        for indice, texto in enumerate(linhas)
    ]


def nome_do_grupo(execucao_id: int) -> str:
    """Retorna o nome do grupo do Channels de uma execução.

    Args:
        execucao_id: id da execução.

    Returns:
        O nome do grupo, como ``execucao_42``.

    English:
        Returns the Channels group name of an execution.

        Args:
            execucao_id: execution id.

        Returns:
            The group name, such as ``execucao_42``.
    """
    return f"execucao_{execucao_id}"


def publicar_linhas(execucao_id: int, linhas: list[LinhaDoLog]) -> bool:
    """Envia um lote de linhas a quem está vendo a execução.

    Args:
        execucao_id: id da execução.
        linhas: linhas novas, em ordem, cada uma com o seu número.

    Returns:
        ``True`` se o envio deu certo; ``False`` se o canal não respondeu.

    English:
        Sends a batch of lines to whoever is watching the execution.

        Args:
            execucao_id: execution id.
            linhas: new lines, in order, each with its number.

        Returns:
            ``True`` if sending worked; ``False`` if the channel did not
            answer.
    """
    return _enviar(execucao_id, {"type": "log.linhas", "linhas": linhas})


def publicar_fim(execucao_id: int, status: str) -> bool:
    """Avisa quem está vendo a execução que ela terminou.

    Deve ser chamada depois de o status final estar gravado no banco: o
    navegador recarrega a página ao receber o aviso.

    Args:
        execucao_id: id da execução.
        status: status final (``sucesso``, ``falha`` ou ``cancelada``).

    Returns:
        ``True`` se o envio deu certo; ``False`` se o canal não respondeu.

    English:
        Tells whoever is watching the execution that it has ended.

        It must be called after the final status is saved to the
        database: the browser reloads the page when it gets the notice.

        Args:
            execucao_id: execution id.
            status: final status (``sucesso``, ``falha`` or
                ``cancelada``).

        Returns:
            ``True`` if sending worked; ``False`` if the channel did not
            answer.
    """
    return _enviar(execucao_id, {"type": "log.fim", "status": status})


def _enviar(execucao_id: int, evento: dict[str, Any]) -> bool:
    """Envia ``evento`` ao grupo da execução, sem deixar o erro subir.

    ``group_send`` é assíncrona; ``async_to_sync`` permite chamá-la do
    código síncrono do worker. O campo ``type`` do evento diz qual método
    do consumer o recebe (``log.linhas`` vira ``log_linhas``).

    Args:
        execucao_id: id da execução.
        evento: evento do Channels, com o campo ``type``.

    Returns:
        ``True`` se o envio deu certo; ``False`` caso contrário.

    English:
        Sends ``evento`` to the execution's group, without letting the
        error escape.

        ``group_send`` is async; ``async_to_sync`` lets the worker's sync
        code call it. The event's ``type`` field says which consumer
        method receives it (``log.linhas`` becomes ``log_linhas``).

        Args:
            execucao_id: execution id.
            evento: Channels event, with the ``type`` field.

        Returns:
            ``True`` if sending worked; ``False`` otherwise.
    """
    camada = get_channel_layer()
    if camada is None:
        return False
    try:
        async_to_sync(camada.group_send)(nome_do_grupo(execucao_id), evento)
    except (OSError, RedisError) as erro:
        logger.warning(
            "Log ao vivo da execução %s indisponível: %s", execucao_id, erro
        )
        return False
    return True
