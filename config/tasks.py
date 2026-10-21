"""Tarefas Celery do app de configurações.

English:
    Celery tasks for the settings app.
"""

import logging

from celery import shared_task

from config.services import limpar_historico
from config.status import registrar_pulso

logger = logging.getLogger(__name__)


@shared_task
def registrar_pulso_agendador() -> None:
    """Grava o pulso que mostra que o agendador está vivo.

    O ``celery beat`` envia esta tarefa a cada minuto. Se ela parar de
    chegar, a chave expira e o status do sistema mostra o agendador como
    parado.

    English:
        Writes the pulse that shows the scheduler is alive.

        ``celery beat`` sends this task every minute. If it stops arriving,
        the key expires and the system status shows the scheduler as
        stopped.
    """
    registrar_pulso()


@shared_task
def limpar_historico_antigo() -> int:
    """Apaga o histórico mais antigo que a retenção configurada.

    O ``celery beat`` envia esta tarefa uma vez por dia, de madrugada.

    Returns:
        Quantidade de execuções apagadas.

    English:
        Deletes history older than the configured retention.

        ``celery beat`` sends this task once a day, overnight.

        Returns:
            Number of deleted executions.
    """
    apagadas = limpar_historico()
    logger.info("Limpeza do histórico: %s execuções apagadas.", apagadas)
    return apagadas
