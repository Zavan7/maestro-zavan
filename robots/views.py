from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Prefetch, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from executions.models import Execucao
from robots.forms import RoboForm
from robots.models import Robo
from robots.services import DisparoRecusado, disparar_execucao
from scheduler.models import formatar_proxima


def _estado_da_agenda(robo, agora):
    agendamentos = list(robo.agendamentos.all())
    ativos = [a for a in agendamentos if a.ativo]

    if ativos:
        proximas = [a.proxima_ocorrencia(agora) for a in ativos]
        proxima = min((p for p in proximas if p), default=None)
        texto = formatar_proxima(proxima, agora) if proxima else "agendado"
        return "agendado", texto
    if agendamentos:
        return "pausado", "pausado"
    return "manual", "manual"


@login_required
def robot_list(request):
    robos = list(
        Robo.objects.prefetch_related(
            Prefetch(
                "execucoes",
                queryset=Execucao.objects.order_by("-id"),
                to_attr="execucoes_recentes",
            ),
            "agendamentos",
        ).order_by("nome")
    )

    agora = timezone.localtime()
    for robo in robos:
        ultima = robo.execucoes_recentes[0] if robo.execucoes_recentes else None
        robo.ultima_execucao = ultima

        if ultima and ultima.status == Execucao.Status.RODANDO:
            robo.estado_agora, robo.texto_agora = "rodando", "rodando"
        elif ultima and ultima.status == Execucao.Status.PENDENTE:
            robo.estado_agora, robo.texto_agora = "rodando", "aguardando"
        else:
            robo.estado_agora, robo.texto_agora = "parado", "parado"

        robo.estado_agenda, robo.texto_agenda = _estado_da_agenda(robo, agora)
        robo.agenda_bloqueada = (
            robo.estado_agenda == "agendado" and robo.status != Robo.Status.ATIVO
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


@permission_required("robots.executar_robo", raise_exception=True)
def robot_start(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        try:
            disparar_execucao(robo, disparado_por=request.user)
        except DisparoRecusado as erro:
            messages.error(request, f"Não é possível iniciar '{robo.nome}': {erro}.")
        else:
            messages.success(request, f"Execução de '{robo.nome}' iniciada.")

    return redirect("robot_list")


@permission_required("robots.executar_robo", raise_exception=True)
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