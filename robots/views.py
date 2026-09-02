from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Prefetch
from robots.models import Robo
from executions.models import Execucao


@login_required
def robot_list(request):
    robos = Robo.objects.prefetch_related(
        Prefetch(
            "execucoes",
            queryset=Execucao.objects.order_by("-id"),
            to_attr="execucoes_recentes",
        )
    )
    return render(request, "robots/list.html", {"robos": robos})