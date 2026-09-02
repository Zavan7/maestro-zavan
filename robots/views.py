from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
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


@login_required
def robot_create(request):
    if request.method == "POST":
        Robo.objects.create(
            nome=request.POST.get("nome"),
            descricao=request.POST.get("descricao", ""),
            caminho_script=request.POST.get("caminho_script"),
            status=request.POST.get("status", Robo.Status.ATIVO),
            responsavel=request.user,
        )
        return redirect("robot_list")

    return render(request, "robots/create.html")