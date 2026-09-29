from django.db import transaction

from executions.models import Execucao
from robots.models import Robo
from robots.tasks import executar_robo


class DisparoRecusado(Exception):
    pass


def disparar_execucao(
    robo, disparado_por=None, origem=Execucao.Origem.MANUAL, agendamento=None
):
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
    )
    transaction.on_commit(lambda: executar_robo.delay(execucao.id))
    return execucao
