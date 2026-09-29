from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from executions.models import Execucao
from robots.models import Robo
from scheduler.forms import AgendamentoForm
from scheduler.models import Agendamento, formatar_proxima


@login_required
def schedule_list(request):
    agendamentos = list(Agendamento.objects.select_related("robo"))

    robos_em_andamento = set(
        Execucao.objects.filter(
            status__in=[Execucao.Status.PENDENTE, Execucao.Status.RODANDO]
        ).values_list("robo_id", flat=True)
    )

    agora = timezone.localtime()
    for agendamento in agendamentos:
        if agendamento.ativo:
            agendamento.proxima = agendamento.proxima_ocorrencia(agora)
            agendamento.estado = "agendado"
            agendamento.texto_estado = formatar_proxima(agendamento.proxima, agora)
        else:
            agendamento.proxima = None
            agendamento.estado = "pausado"
            agendamento.texto_estado = "pausado"

        if agendamento.robo_id in robos_em_andamento:
            agendamento.estado_robo = "rodando"
        else:
            agendamento.estado_robo = "parado"

        agendamento.bloqueado = (
            agendamento.ativo and agendamento.robo.status != Robo.Status.ATIVO
        )

    agendamentos.sort(
        key=lambda a: (0, a.proxima) if a.ativo else (1, a.horario)
    )

    return render(request, "scheduler/list.html", {"agendamentos": agendamentos})


@permission_required("scheduler.add_agendamento", raise_exception=True)
def schedule_create(request):
    if request.method == "POST":
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            agendamento = form.save(commit=False)
            agendamento.criado_por = request.user
            agendamento.save()
            messages.success(request, f"Agendamento de '{agendamento.robo.nome}' criado.")
            return redirect("schedule_list")
    else:
        form = AgendamentoForm()

    return render(request, "scheduler/form.html", {"form": form, "titulo": "novo"})


@permission_required("scheduler.change_agendamento", raise_exception=True)
def schedule_edit(request, pk):
    agendamento = get_object_or_404(Agendamento, pk=pk)

    if request.method == "POST":
        form = AgendamentoForm(request.POST, instance=agendamento)
        if form.is_valid():
            form.save()
            messages.success(request, f"Agendamento de '{agendamento.robo.nome}' salvo.")
            return redirect("schedule_list")
    else:
        form = AgendamentoForm(instance=agendamento)

    return render(request, "scheduler/form.html", {"form": form, "titulo": f"{pk}/editar"})


@permission_required("scheduler.change_agendamento", raise_exception=True)
def schedule_toggle(request, pk):
    agendamento = get_object_or_404(Agendamento.objects.select_related("robo"), pk=pk)

    if request.method == "POST":
        agendamento.ativo = not agendamento.ativo
        agendamento.save(update_fields=["ativo"])
        acao = "retomado" if agendamento.ativo else "pausado"
        messages.success(request, f"Agendamento de '{agendamento.robo.nome}' {acao}.")

    return redirect("schedule_list")


@permission_required("scheduler.delete_agendamento", raise_exception=True)
def schedule_delete(request, pk):
    agendamento = get_object_or_404(Agendamento.objects.select_related("robo"), pk=pk)

    if request.method == "POST":
        agendamento.delete()
        messages.success(request, f"Agendamento de '{agendamento.robo.nome}' excluído.")
        return redirect("schedule_list")

    return render(request, "scheduler/delete_confirm.html", {"agendamento": agendamento})
