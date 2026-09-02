from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from robots.models import Robo
from executions.models import Execucao


@login_required
def home(request):
    contexto = {
        "total_robos": Robo.objects.count(),
        "robos_ativos": Robo.objects.filter(status=Robo.Status.ATIVO).count(),
        "robos_manutencao": Robo.objects.filter(status=Robo.Status.MANUTENCAO).count(),
        "execucoes_recentes": Execucao.objects.select_related("robo").order_by("-id")[:5],
    }
    return render(request, "accounts/home.html", contexto)