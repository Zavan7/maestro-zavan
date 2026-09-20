from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Prefetch, ProtectedError
from robots.models import Robo
from executions.models import Execucao
from django.utils import timezone

from robots.forms import RoboForm

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
        form = RoboForm(request.POST)
        if form.is_valid():
            robo = form.save(commit=False)
            robo.responsavel = request.user
            robo.save()
            return redirect("robot_list")
    else:
        form = RoboForm()

    return render(request, "robots/create.html", {"form": form})


@login_required
def robot_edit(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        form = RoboForm(request.POST, instance=robo)
        if form.is_valid():
            form.save()
            return redirect("robot_list")
    else:
        form = RoboForm(instance=robo)

    return render(request, "robots/edit.html", {"form": form, "robo": robo})


@login_required
def robot_exclusion(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        try:
            robo.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Não é possível excluir '{robo.nome}': existem execuções associadas a ele."
            )
            return redirect("robot_list")

        return redirect("robot_list")

    return render(request, "robots/exclusion_confirm.html", {"robo": robo})


@login_required
def robot_start(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        ja_rodando = robo.execucoes.filter(status=Execucao.Status.RODANDO).exists()

        if not ja_rodando:
            # TODO (Nível 2/3): aqui entra o disparo real via WebSocket/Celery
            # pro agente que roda o script na máquina. Por enquanto, só
            # simulamos o estado no banco.
            Execucao.objects.create(
                robo=robo,
                status=Execucao.Status.RODANDO,
                iniciado_em=timezone.now(),
                disparado_por=request.user,
            )

    return redirect("robot_list")


@login_required
def robot_stop(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        execucao = robo.execucoes.filter(status=Execucao.Status.RODANDO).last()

        if execucao:
            # TODO (Nível 2/3): aqui entra o comando real de parada via
            # WebSocket pro agente. Por enquanto, marcamos como sucesso
            # manualmente.
            execucao.status = Execucao.Status.SUCESSO
            execucao.finalizado_em = timezone.now()
            execucao.save()

    return redirect("robot_list")