from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Prefetch, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from executions.models import Execucao
from robots.forms import RoboForm
from robots.models import Robo
from robots.tasks import executar_robo


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


@permission_required("robots.add_robo", raise_exception=True)
def robot_create(request):
    if request.method == "POST":
        form = RoboForm(request.POST)
        if form.is_valid():
            robo = form.save(commit=False)
            robo.responsavel = request.user
            robo.save()
            messages.success(request, f"Robô '{robo.nome}' cadastrado.")
            return redirect("robot_list")
    else:
        form = RoboForm()

    return render(request, "robots/create.html", {"form": form})


@permission_required("robots.change_robo", raise_exception=True)
def robot_edit(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        form = RoboForm(request.POST, instance=robo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Robô '{robo.nome}' salvo.")
            return redirect("robot_list")
    else:
        form = RoboForm(instance=robo)

    return render(request, "robots/edit.html", {"form": form, "robo": robo})


@permission_required("robots.delete_robo", raise_exception=True)
def robot_exclusion(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        try:
            robo.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Não é possível excluir '{robo.nome}': existem execuções associadas a ele.",
            )
            return redirect("robot_list")

        messages.success(request, f"Robô '{robo.nome}' excluído.")
        return redirect("robot_list")

    return render(request, "robots/exclusion_confirm.html", {"robo": robo})


@login_required
def robot_start(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        if robo.status != Robo.Status.ATIVO:
            messages.error(
                request,
                f"Não é possível iniciar '{robo.nome}': robô está {robo.get_status_display().lower()}.",
            )
            return redirect("robot_list")

        em_andamento = robo.execucoes.filter(
            status__in=[Execucao.Status.PENDENTE, Execucao.Status.RODANDO]
        ).exists()

        if em_andamento:
            messages.error(
                request,
                f"'{robo.nome}' já tem uma execução em andamento.",
            )
            return redirect("robot_list")

        execucao = Execucao.objects.create(
            robo=robo,
            status=Execucao.Status.PENDENTE,
            disparado_por=request.user,
        )
        transaction.on_commit(lambda: executar_robo.delay(execucao.id))
        messages.success(request, f"Execução de '{robo.nome}' iniciada.")

    return redirect("robot_list")


@login_required
def robot_stop(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        execucao = robo.execucoes.filter(status=Execucao.Status.RODANDO).last()

        if execucao:
            # TODO: com o agente Go, aqui o Django manda o comando de parada
            # via WebSocket e o agente encerra o processo de verdade.
            # Por enquanto, só marca o registro como finalizado.
            execucao.status = Execucao.Status.SUCESSO
            execucao.finalizado_em = timezone.now()
            execucao.save()

    return redirect("robot_list")