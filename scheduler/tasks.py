"""Tarefas Celery do app de agendamentos.

English:
    Celery tasks for the schedules app.
"""
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from executions.models import Execucao
from robots.services import DisparoRecusado, disparar_execucao
from scheduler.models import DIAS_DA_SEMANA, Agendamento

logger = logging.getLogger(__name__)


@shared_task
def verificar_agendamentos():
    """Dispara os agendamentos que vencem no minuto atual.

    O ``celery beat`` chama esta tarefa uma vez por minuto. Ela:

    1. Busca os agendamentos ativos com o horário deste minuto e o dia de
       hoje marcado.
    2. "Reivindica" cada um com um ``UPDATE`` condicional: só atualiza
       ``ultimo_disparo`` se ele ainda não foi preenchido neste minuto. O
       ``UPDATE`` é atômico no banco, então se dois workers rodarem juntos
       só um consegue, e o robô não dispara duas vezes.
    3. Dispara pelo mesmo serviço do botão (``disparar_execucao``), dentro
       de ``transaction.atomic`` para o ``on_commit`` funcionar.
    4. Se o disparo for recusado (robô em manutenção, por exemplo), só
       registra um aviso no log e segue para o próximo.

    Returns:
        Quantidade de execuções disparadas neste minuto.

    English:
        Triggers the schedules that are due in the current minute.

        ``celery beat`` calls this task once a minute. It:

        1. Fetches the active schedules set for this minute with today
           checked.
        2. "Claims" each one with a conditional ``UPDATE``: it only updates
           ``ultimo_disparo`` if it has not been set in this minute yet.
           The ``UPDATE`` is atomic in the database, so if two workers run
           together only one succeeds, and the robot never fires twice.
        3. Triggers through the same service as the button
           (``disparar_execucao``), inside ``transaction.atomic`` so
           ``on_commit`` works.
        4. If the trigger is refused (robot under maintenance, for
           example), it only logs a warning and moves on to the next one.

        Returns:
            Number of executions triggered in this minute.
    """
    agora = timezone.localtime()
    inicio_do_minuto = agora.replace(second=0, microsecond=0)
    dia_de_hoje = DIAS_DA_SEMANA[agora.weekday()]

    vencidos = Agendamento.objects.select_related("robo").filter(
        ativo=True,
        horario=inicio_do_minuto.time(),
        **{dia_de_hoje: True},
    )

    disparados = 0
    for agendamento in vencidos:
        reivindicado = (
            Agendamento.objects.filter(pk=agendamento.pk)
            .exclude(ultimo_disparo__gte=inicio_do_minuto)
            .update(ultimo_disparo=agora)
        )
        if not reivindicado:
            continue

        try:
            with transaction.atomic():
                disparar_execucao(
                    agendamento.robo,
                    origem=Execucao.Origem.AGENDAMENTO,
                    agendamento=agendamento,
                )
        except DisparoRecusado as erro:
            logger.warning(
                "Agendamento %s não disparou: %s", agendamento, erro
            )
        else:
            disparados += 1

    return disparados
