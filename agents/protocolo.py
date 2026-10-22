"""Regras do protocolo do agente: o que fazer com cada mensagem recebida.

Funções síncronas, sem WebSocket: o ``AgenteConsumer`` as chama com
``database_sync_to_async``. Toda mensagem é validada antes de tocar no
banco, e um agente só mexe nas execuções dos robôs dele. Uma mensagem
inválida levanta ``MensagemInvalida``, que o consumer devolve ao agente
como ``{"tipo": "erro"}``, sem derrubar a conexão.

Mensagens do agente para o Maestro:

- ``{"tipo": "heartbeat"}``
- ``{"tipo": "iniciado", "execucao_id": 42}``
- ``{"tipo": "log", "execucao_id": 42, "linhas": ["...", "..."]}``
- ``{"tipo": "fim", "execucao_id": 42, "motivo": "concluido",
  "codigo_saida": 0}``

English:
    Agent protocol rules: what to do with each message received.

    Sync functions, no WebSocket: ``AgenteConsumer`` calls them with
    ``database_sync_to_async``. Every message is validated before
    touching the database, and an agent only handles its own robots'
    executions. An invalid message raises ``MensagemInvalida``, which the
    consumer sends back to the agent as ``{"tipo": "erro"}``, without
    dropping the connection.

    Messages from the agent to Maestro:

    - ``{"tipo": "heartbeat"}``
    - ``{"tipo": "iniciado", "execucao_id": 42}``
    - ``{"tipo": "log", "execucao_id": 42, "linhas": ["...", "..."]}``
    - ``{"tipo": "fim", "execucao_id": 42, "motivo": "concluido",
      "codigo_saida": 0}``
"""

from typing import Any

from django.utils import timezone

from agents.models import Agente, hash_do_token
from config.models import ConfiguracaoSistema
from executions.ao_vivo import LinhaDoLog, publicar_linhas
from executions.models import Execucao
from robots.conclusao import desfecho, finalizar_execucao
from robots.executor import Motivo

MAX_LINHAS_POR_MENSAGEM = 1_000
MAX_CARACTERES_POR_LINHA = 10_000


class MensagemInvalida(Exception):
    """Indica uma mensagem do agente que não segue o protocolo.

    A mensagem da exceção diz o motivo e volta para o agente.

    English:
        Signals an agent message that does not follow the protocol.

        The exception message states the reason and goes back to the
        agent.
    """


def autenticar(token: str) -> Agente | None:
    """Encontra o agente ativo dono do token.

    A busca é pelo hash: o token em texto nunca é guardado.

    Args:
        token: token enviado pelo agente no cabeçalho ``Authorization``.

    Returns:
        O agente, ou ``None`` se o token não vale.

    English:
        Finds the active agent that owns the token.

        The lookup is by hash: the plain token is never stored.

        Args:
            token: token sent by the agent in the ``Authorization``
                header.

        Returns:
            The agent, or ``None`` if the token is not valid.
    """
    return Agente.objects.filter(
        token_hash=hash_do_token(token), ativo=True
    ).first()


def credencial_vale(agente_id: int, token_hash: str) -> bool:
    """Diz se o agente continua ativo e com o mesmo token da conexão.

    O aviso de "desconectar" pelo Redis pode não chegar (Redis fora no
    instante da troca, por exemplo); por isso a conexão confere isto a
    cada mensagem, e não só ao conectar. Um token trocado ou um agente
    desativado deixa de valer na mensagem seguinte.

    Args:
        agente_id: id do agente da conexão.
        token_hash: hash do token com que a conexão foi aberta.

    Returns:
        ``True`` se o agente está ativo e o token não mudou.

    English:
        Tells whether the agent is still active and with the connection's
        token.

        The "disconnect" notice through Redis may not arrive (Redis down
        at the moment of the change, for example); that is why the
        connection checks this on every message, not only on connect. A
        replaced token or a deactivated agent stops working on the next
        message.

        Args:
            agente_id: id of the connection's agent.
            token_hash: hash of the token the connection was opened with.

        Returns:
            ``True`` if the agent is active and the token did not change.
    """
    return Agente.objects.filter(
        pk=agente_id, ativo=True, token_hash=token_hash
    ).exists()


def registrar_sinal(agente_id: int) -> None:
    """Anota que o agente deu sinal agora.

    Args:
        agente_id: id do agente.

    English:
        Records that the agent signalled just now.

        Args:
            agente_id: agent id.
    """
    Agente.objects.filter(pk=agente_id).update(ultimo_sinal=timezone.now())


def ler_inteiro(mensagem: dict[str, Any], campo: str) -> int:
    """Lê um campo inteiro obrigatório da mensagem.

    ``bool`` é recusado de propósito: em Python, ``True`` também é
    ``int``.

    Args:
        mensagem: mensagem recebida do agente.
        campo: nome do campo.

    Returns:
        O valor do campo.

    Raises:
        MensagemInvalida: se o campo falta ou não é inteiro.

    English:
        Reads a required integer field from the message.

        ``bool`` is refused on purpose: in Python, ``True`` is also an
        ``int``.

        Args:
            mensagem: message received from the agent.
            campo: field name.

        Returns:
            The field value.

        Raises:
            MensagemInvalida: if the field is missing or not an integer.
    """
    valor = mensagem.get(campo)
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise MensagemInvalida(f"campo '{campo}' precisa ser um inteiro")
    return valor


def confirmar_inicio(agente_id: int, execucao_id: int) -> bool:
    """Reivindica a execução quando o agente avisa que começou.

    Mesmo ``UPDATE`` condicional do worker: só uma execução ``PENDENTE``
    deste agente vira ``RODANDO``. Se ela foi cancelada no caminho, nada
    muda e o consumer manda o agente parar.

    Args:
        agente_id: id do agente que avisou.
        execucao_id: id da execução.

    Returns:
        ``True`` se a execução foi reivindicada.

    English:
        Claims the execution when the agent says it started.

        Same conditional ``UPDATE`` as the worker: only a ``PENDENTE``
        execution of this agent becomes ``RODANDO``. If it was cancelled
        along the way, nothing changes and the consumer tells the agent to
        stop.

        Args:
            agente_id: id of the agent that reported.
            execucao_id: execution id.

        Returns:
            ``True`` if the execution was claimed.
    """
    reivindicadas = Execucao.objects.filter(
        pk=execucao_id,
        robo__agente_id=agente_id,
        status=Execucao.Status.PENDENTE,
    ).update(status=Execucao.Status.RODANDO, iniciado_em=timezone.now())
    return reivindicadas == 1


def receber_linhas(agente_id: int, mensagem: dict[str, Any]) -> None:
    """Acrescenta ao log as linhas enviadas e as repassa à tela.

    Grava no banco antes de publicar, como o worker, para o consumer da
    tela nunca perder linhas. Só o fim do log é guardado
    (``limite_log``).

    Args:
        agente_id: id do agente que enviou.
        mensagem: mensagem ``log`` com ``execucao_id`` e ``linhas``.

    Raises:
        MensagemInvalida: se as linhas não são uma lista de textos dentro
            dos limites, ou se a execução não está rodando neste agente.

    English:
        Appends the lines sent to the log and relays them to the page.

        It saves to the database before publishing, like the worker, so
        the page consumer never loses lines. Only the end of the log is
        kept (``limite_log``).

        Args:
            agente_id: id of the agent that sent it.
            mensagem: ``log`` message with ``execucao_id`` and ``linhas``.

        Raises:
            MensagemInvalida: if the lines are not a list of strings
                within the limits, or if the execution is not running on
                this agent.
    """
    execucao_id = ler_inteiro(mensagem, "execucao_id")
    linhas = mensagem.get("linhas")
    if not isinstance(linhas, list) or not all(
        isinstance(linha, str) for linha in linhas
    ):
        raise MensagemInvalida("campo 'linhas' precisa ser lista de textos")
    if len(linhas) > MAX_LINHAS_POR_MENSAGEM or any(
        len(linha) > MAX_CARACTERES_POR_LINHA for linha in linhas
    ):
        raise MensagemInvalida("lote de linhas acima do limite")
    if not linhas:
        return

    execucao = _execucao_do_agente(
        agente_id, execucao_id, [Execucao.Status.RODANDO]
    )
    limite = ConfiguracaoSistema.atual().limite_log
    primeira = execucao.total_linhas + 1
    texto = "\n".join(filter(None, [execucao.log, *linhas]))
    Execucao.objects.filter(pk=execucao_id).update(
        log=texto[-limite:], total_linhas=execucao.total_linhas + len(linhas)
    )
    publicar_linhas(
        execucao_id,
        [
            LinhaDoLog(numero=primeira + indice, texto=linha)
            for indice, linha in enumerate(linhas)
        ],
    )


def receber_fim(agente_id: int, mensagem: dict[str, Any]) -> None:
    """Encerra a execução com o motivo e o código que o agente informou.

    O status final sai das mesmas regras do worker
    (``robots.conclusao``), inclusive a nova tentativa. Uma execução que
    já foi encerrada (cancelada porque o agente ficou offline, por
    exemplo) é ignorada.

    Args:
        agente_id: id do agente que enviou.
        mensagem: mensagem ``fim`` com ``execucao_id``, ``motivo`` e, se
            o processo rodou, ``codigo_saida``.

    Raises:
        MensagemInvalida: se o motivo é desconhecido, o código não é
            inteiro ou a execução não é deste agente.

    English:
        Ends the execution with the reason and code the agent reported.

        The final status comes from the same rules as the worker
        (``robots.conclusao``), including the new attempt. An execution
        that has already ended (cancelled because the agent went offline,
        for example) is ignored.

        Args:
            agente_id: id of the agent that sent it.
            mensagem: ``fim`` message with ``execucao_id``, ``motivo`` and,
                if the process ran, ``codigo_saida``.

        Raises:
            MensagemInvalida: if the reason is unknown, the code is not an
                integer or the execution does not belong to this agent.
    """
    execucao_id = ler_inteiro(mensagem, "execucao_id")
    try:
        motivo = Motivo(mensagem.get("motivo"))
    except ValueError:
        raise MensagemInvalida("campo 'motivo' desconhecido") from None
    codigo_saida = (
        ler_inteiro(mensagem, "codigo_saida")
        if mensagem.get("codigo_saida") is not None
        else None
    )

    execucao = _execucao_do_agente(agente_id, execucao_id)
    if execucao.status not in (
        Execucao.Status.PENDENTE,
        Execucao.Status.RODANDO,
    ):
        return

    timeout = (
        execucao.robo.timeout_segundos
        or ConfiguracaoSistema.atual().timeout_padrao_segundos
    )
    fim = desfecho(motivo, codigo_saida, timeout)
    if fim.aviso:
        execucao.log = "\n".join(filter(None, [execucao.log, fim.aviso]))
        execucao.total_linhas += 1
    finalizar_execucao(execucao, fim)


def _execucao_do_agente(
    agente_id: int,
    execucao_id: int,
    status_aceitos: list[Execucao.Status] | None = None,
) -> Execucao:
    """Busca uma execução de um robô deste agente.

    Args:
        agente_id: id do agente.
        execucao_id: id da execução.
        status_aceitos: se informado, a execução precisa estar num deles.

    Returns:
        A execução, com o robô.

    Raises:
        MensagemInvalida: se a execução não existe, é de outro agente ou
            está num status não aceito.

    English:
        Fetches an execution of one of this agent's robots.

        Args:
            agente_id: agent id.
            execucao_id: execution id.
            status_aceitos: if given, the execution must be in one of
                them.

        Returns:
            The execution, with its robot.

        Raises:
            MensagemInvalida: if the execution does not exist, belongs to
                another agent or is in a status not accepted.
    """
    execucao = (
        Execucao.objects.select_related("robo", "disparado_por", "agendamento")
        .filter(pk=execucao_id, robo__agente_id=agente_id)
        .first()
    )
    if execucao is None:
        raise MensagemInvalida(f"execução {execucao_id} não é deste agente")
    if status_aceitos is not None and execucao.status not in status_aceitos:
        raise MensagemInvalida(
            f"execução {execucao_id} não está rodando ({execucao.status})"
        )
    return execucao
