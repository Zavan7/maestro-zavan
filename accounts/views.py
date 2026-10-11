"""Views do painel inicial do Maestro.

O painel junta três visões: quantos robôs há em cada status, a
atividade dos últimos dias e as execuções mais recentes. As contas
pesadas são feitas pelo banco (``annotate`` e ``Count``), não em loops
no Python, para o painel continuar rápido com muitos registros.

English:
    Views for Maestro's home dashboard.

    The dashboard combines three views: how many robots are in each
    status, recent daily activity and the latest executions. The heavy
    counting is done by the database (``annotate`` and ``Count``), not
    in Python loops, so the dashboard stays fast with many records.
"""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from executions.models import Execucao
from robots.models import Robo

DIAS_ATIVIDADE = 14


def _distribuicao_por_status():
    """Conta os robôs por status para o gráfico do painel.

    Faz uma única consulta agrupada (``GROUP BY status``) e depois percorre
    ``Robo.Status.choices``. Percorrer as choices, e não o resultado da
    consulta, garante que todo status apareça no gráfico, mesmo os que têm
    zero robôs.

    Returns:
        Tupla ``(distribuicao, total)``. ``distribuicao`` é uma lista de
        dicionários com ``status``, ``rotulo``, ``total`` e ``percentual``;
        ``total`` é a quantidade de robôs cadastrados.

    English:
        Counts robots by status for the dashboard chart.

        Runs a single grouped query (``GROUP BY status``) and then walks
        ``Robo.Status.choices``. Walking the choices, not the query result,
        guarantees every status shows up in the chart, even those with
        zero robots.

        Returns:
            Tuple ``(distribuicao, total)``. ``distribuicao`` is a list of
            dicts with ``status``, ``rotulo``, ``total`` and
            ``percentual``; ``total`` is the number of registered robots.
    """
    por_status = dict(
        Robo.objects.values_list("status").annotate(total=Count("id"))
    )
    total = sum(por_status.values())

    distribuicao = [
        {
            "status": valor,
            "rotulo": rotulo,
            "total": por_status.get(valor, 0),
            "percentual": (
                por_status.get(valor, 0) / total * 100 if total else 0
            ),
        }
        for valor, rotulo in Robo.Status.choices
    ]
    return distribuicao, total


def _atividade_recente():
    """Monta o histórico diário de sucessos e falhas dos últimos dias.

    Funciona em três passos:

    1. O banco conta as execuções por dia e status
       (``TruncDate`` + ``Count``).
    2. As contagens viram um dicionário ``{dia: {status: total}}``.
    3. Um loop cria uma entrada para cada um dos ``DIAS_ATIVIDADE`` dias,
       inclusive os sem execução, e calcula a altura de cada barra em
       relação ao dia mais movimentado (que vira 100%).

    Returns:
        Lista com um dicionário por dia, do mais antigo até hoje, com
        ``dia``, ``sucesso``, ``falha``, ``altura_sucesso`` e
        ``altura_falha``.

    English:
        Builds the daily history of successes and failures for recent days.

        It works in three steps:

        1. The database counts executions per day and status
           (``TruncDate`` + ``Count``).
        2. The counts become a ``{day: {status: total}}`` dict.
        3. A loop creates one entry for each of the ``DIAS_ATIVIDADE``
           days, including days without executions, and computes each
           bar's height relative to the busiest day (which becomes 100%).

        Returns:
            List with one dict per day, oldest to today, with ``dia``,
            ``sucesso``, ``falha``, ``altura_sucesso`` and
            ``altura_falha``.
    """
    inicio = timezone.localdate() - timedelta(days=DIAS_ATIVIDADE - 1)

    contagens = (
        Execucao.objects.filter(iniciado_em__date__gte=inicio)
        .annotate(dia=TruncDate("iniciado_em"))
        .values("dia", "status")
        .annotate(total=Count("id"))
    )

    por_dia = {}
    for linha in contagens:
        por_dia.setdefault(linha["dia"], {})[linha["status"]] = linha["total"]

    atividade = []
    for deslocamento in range(DIAS_ATIVIDADE):
        dia = inicio + timedelta(days=deslocamento)
        contagem = por_dia.get(dia, {})
        atividade.append({
            "dia": dia,
            "sucesso": contagem.get(Execucao.Status.SUCESSO, 0),
            "falha": contagem.get(Execucao.Status.FALHA, 0),
        })

    maior = max(
        (d["sucesso"] + d["falha"] for d in atividade), default=0
    ) or 1
    for d in atividade:
        d["altura_sucesso"] = d["sucesso"] / maior * 100
        d["altura_falha"] = d["falha"] / maior * 100

    return atividade


@login_required
def home(request):
    """Exibe o painel com robôs por status, atividade e últimas execuções.

    ``@login_required`` manda quem não está logado para a tela de login.
    Nas execuções recentes, ``select_related`` traz o robô e o usuário na
    mesma consulta, evitando o problema N+1 (uma consulta extra por linha
    da tabela).

    Args:
        request: requisição HTTP do usuário logado.

    Returns:
        A página ``accounts/home.html`` renderizada.

    English:
        Shows the dashboard with robots by status, activity and latest runs.

        ``@login_required`` sends anyone not logged in to the login page.
        For the recent executions, ``select_related`` fetches the robot and
        the user in the same query, avoiding the N+1 problem (one extra
        query per table row).

        Args:
            request: HTTP request from the logged-in user.

        Returns:
            The rendered ``accounts/home.html`` page.
    """
    distribuicao, total_robos = _distribuicao_por_status()

    contexto = {
        "total_robos": total_robos,
        "distribuicao": distribuicao,
        "atividade": _atividade_recente(),
        "execucoes_recentes": (
            Execucao.objects.select_related(
                "robo", "disparado_por"
            ).order_by("-id")[:12]
        ),
    }
    return render(request, "accounts/home.html", contexto)
