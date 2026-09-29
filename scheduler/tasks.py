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
            logger.warning("Agendamento %s não disparou: %s", agendamento, erro)
        else:
            disparados += 1

    return disparados