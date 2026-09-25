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
    por_status = dict(Robo.objects.values_list("status").annotate(total=Count("id")))
    total = sum(por_status.values())

    distribuicao = [
        {
            "status": valor,
            "rotulo": rotulo,
            "total": por_status.get(valor, 0),
            "percentual": por_status.get(valor, 0) / total * 100 if total else 0,
        }
        for valor, rotulo in Robo.Status.choices
    ]
    return distribuicao, total


def _atividade_recente():
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

    maior = max((d["sucesso"] + d["falha"] for d in atividade), default=0) or 1
    for d in atividade:
        d["altura_sucesso"] = d["sucesso"] / maior * 100
        d["altura_falha"] = d["falha"] / maior * 100

    return atividade


@login_required
def home(request):
    distribuicao, total_robos = _distribuicao_por_status()

    contexto = {
        "total_robos": total_robos,
        "distribuicao": distribuicao,
        "atividade": _atividade_recente(),
        "execucoes_recentes": (
            Execucao.objects.select_related("robo", "disparado_por").order_by("-id")[:12]
        ),
    }
    return render(request, "accounts/home.html", contexto)