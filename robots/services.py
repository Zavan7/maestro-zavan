"""Serviços do app de robôs.

Uma "camada de serviço" guarda regras de negócio que mais de um lugar
precisa, sem depender de HTTP. Aqui está ``disparar_execucao``, o único
caminho para iniciar um robô: tanto o botão "iniciar" quanto o
agendador passam por ela, então a regra fica escrita uma vez só.

English:
    Services for the robots app.

    A "service layer" holds business rules that more than one place
    needs, without depending on HTTP. Here lives ``disparar_execucao``,
    the only way to start a robot: both the "start" button and the
    scheduler go through it, so the rule is written only once.
"""

from django.contrib.auth.models import User
from django.db import transaction

from executions.models import Execucao
from robots.models import Robo
from robots.tasks import executar_robo
from scheduler.models import Agendamento


class DisparoRecusado(Exception):
    """Indica que o robô não pode ser disparado agora.

    A mensagem da exceção diz o motivo, já pronta para o usuário. Cada
    chamador decide o que fazer com ela: a view mostra com
    ``messages.error`` e o agendador grava no log.

    English:
        Signals that the robot cannot be triggered right now.

        The exception message states the reason, ready for the user. Each
        caller decides what to do with it: the view shows it with
        ``messages.error`` and the scheduler writes it to the log.
    """


def disparar_execucao(
    robo: Robo,
    disparado_por: User | None = None,
    origem: Execucao.Origem = Execucao.Origem.MANUAL,
    agendamento: Agendamento | None = None,
    tentativa: int = 1,
) -> Execucao:
    """Cria uma execução pendente e envia a tarefa ao Celery após o commit.

    Passo a passo:

    1. Recusa robôs que não estão ativos.
    2. Recusa se já existe execução pendente ou rodando, para o mesmo
       robô não rodar duas vezes ao mesmo tempo.
    3. Cria a ``Execucao`` com status ``PENDENTE``.
    4. Agenda o envio da tarefa com ``transaction.on_commit``.

    Por que ``on_commit``? Se a tarefa fosse enviada na hora, o worker
    poderia procurar a execução antes de a transação ser gravada no banco
    e não encontrá-la. Com ``on_commit``, ela só sai depois do commit.

    Args:
        robo: robô a ser executado.
        disparado_por: usuário que clicou em "iniciar", ou ``None`` quando
            o disparo é automático.
        origem: de onde veio o disparo (``MANUAL`` ou ``AGENDAMENTO``).
        agendamento: agendamento que originou o disparo, se houver.
        tentativa: número da tentativa; maior que 1 quando é uma nova
            tentativa depois de uma falha.

    Returns:
        A ``Execucao`` criada, com status ``PENDENTE``.

    Raises:
        DisparoRecusado: se o robô não está ativo ou já tem uma execução
            pendente ou rodando.

    English:
        Creates a pending execution and sends the Celery task after commit.

        Step by step:

        1. Refuses robots that are not active.
        2. Refuses if there is already a pending or running execution, so
           the same robot never runs twice at once.
        3. Creates the ``Execucao`` with ``PENDENTE`` status.
        4. Schedules sending the task with ``transaction.on_commit``.

        Why ``on_commit``? If the task were sent right away, the worker
        could look up the execution before the transaction is saved to the
        database and not find it. With ``on_commit``, it only goes out
        after the commit.

        Args:
            robo: robot to run.
            disparado_por: user who clicked "start", or ``None`` when the
                trigger is automatic.
            origem: where the trigger came from (``MANUAL`` or
                ``AGENDAMENTO``).
            agendamento: schedule that caused the trigger, if any.
            tentativa: attempt number; greater than 1 when it is a new
                attempt after a failure.

        Returns:
            The created ``Execucao``, with ``PENDENTE`` status.

        Raises:
            DisparoRecusado: if the robot is not active or already has a
                pending or running execution.
    """
    if robo.status != Robo.Status.ATIVO:
        raise DisparoRecusado(f"robô está {robo.get_status_display().lower()}")

    em_andamento = robo.execucoes.filter(
        status__in=[Execucao.Status.PENDENTE, Execucao.Status.RODANDO]
    ).exists()
    if em_andamento:
        raise DisparoRecusado("já tem uma execução em andamento")

    execucao = Execucao.objects.create(
        robo=robo,
        status=Execucao.Status.PENDENTE,
        disparado_por=disparado_por,
        origem=origem,
        agendamento=agendamento,
        tentativa=tentativa,
    )
    transaction.on_commit(lambda: executar_robo.delay(execucao.id))
    return execucao
