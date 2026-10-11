"""Views do app de agendamentos.

English:
    Views for the schedules app.
"""
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
    """Lista os agendamentos com o estado de cada um.

    Para cada agendamento, a view calcula:

    - ``estado`` e ``texto_estado``: ``agendado`` (com a próxima
      ocorrência) ou ``pausado``;
    - ``estado_robo``: ``rodando`` ou ``parado``, a partir de um ``set``
      com os robôs em andamento, montado com uma única consulta;
    - ``bloqueado``: agendamento ativo de um robô que não está ativo, que
      vai ser recusado quando chegar a hora.

    Por fim, ordena em Python: ativos primeiro, pela próxima ocorrência;
    depois os pausados, pelo horário. A tupla na ``key`` (``(0, ...)`` e
    ``(1, ...)``) é o truque que separa os dois grupos.

    Args:
        request: requisição HTTP do usuário logado.

    Returns:
        A página ``scheduler/list.html`` renderizada.

    English:
        Lists the schedules with each one's state.

        For each schedule, the view computes:

        - ``estado`` and ``texto_estado``: ``agendado`` (with the next run)
          or ``pausado``;
        - ``estado_robo``: ``rodando`` or ``parado``, from a ``set`` of
          running robots built with a single query;
        - ``bloqueado``: an active schedule for a robot that is not active,
          which will be refused when the time comes.

        Finally, it sorts in Python: active ones first, by next run; then
        the paused ones, by time. The tuple in ``key`` (``(0, ...)`` and
        ``(1, ...)``) is the trick that separates the two groups.

        Args:
            request: HTTP request from the logged-in user.

        Returns:
            The rendered ``scheduler/list.html`` page.
    """
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
            agendamento.texto_estado = formatar_proxima(
                agendamento.proxima, agora
            )
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

    return render(
        request, "scheduler/list.html", {"agendamentos": agendamentos}
    )


@permission_required("scheduler.add_agendamento", raise_exception=True)
def schedule_create(request):
    """Cria um agendamento, registrando o usuário logado como criador.

    Args:
        request: requisição HTTP; exige a permissão
            ``scheduler.add_agendamento``.

    Returns:
        Redireciona para a lista após salvar, ou renderiza o formulário.

    English:
        Creates a schedule, recording the logged-in user as its creator.

        Args:
            request: HTTP request; requires the
                ``scheduler.add_agendamento`` permission.

        Returns:
            Redirects to the list after saving, or renders the form.
    """
    if request.method == "POST":
        form = AgendamentoForm(request.POST)
        if form.is_valid():
            agendamento = form.save(commit=False)
            agendamento.criado_por = request.user
            agendamento.save()
            messages.success(
                request,
                f"Agendamento de '{agendamento.robo.nome}' criado.",
            )
            return redirect("schedule_list")
    else:
        form = AgendamentoForm()

    return render(
        request, "scheduler/form.html", {"form": form, "titulo": "novo"}
    )


@permission_required("scheduler.change_agendamento", raise_exception=True)
def schedule_edit(request, pk):
    """Edita um agendamento existente.

    Args:
        request: requisição HTTP; exige a permissão
            ``scheduler.change_agendamento``.
        pk: chave primária do agendamento.

    Returns:
        Redireciona para a lista após salvar, ou renderiza o formulário.

    English:
        Edits an existing schedule.

        Args:
            request: HTTP request; requires the
                ``scheduler.change_agendamento`` permission.
            pk: primary key of the schedule.

        Returns:
            Redirects to the list after saving, or renders the form.
    """
    agendamento = get_object_or_404(Agendamento, pk=pk)

    if request.method == "POST":
        form = AgendamentoForm(request.POST, instance=agendamento)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Agendamento de '{agendamento.robo.nome}' salvo.",
            )
            return redirect("schedule_list")
    else:
        form = AgendamentoForm(instance=agendamento)

    return render(
        request,
        "scheduler/form.html",
        {"form": form, "titulo": f"{pk}/editar"},
    )


@permission_required("scheduler.change_agendamento", raise_exception=True)
def schedule_toggle(request, pk):
    """Pausa um agendamento ativo ou retoma um pausado.

    Só age em POST. O ``update_fields=["ativo"]`` grava apenas essa
    coluna, sem sobrescrever outros campos que a tarefa possa ter
    atualizado no meio tempo (como ``ultimo_disparo``).

    Args:
        request: requisição HTTP; exige a permissão
            ``scheduler.change_agendamento``.
        pk: chave primária do agendamento.

    Returns:
        Sempre redireciona para a lista de agendamentos.

    English:
        Pauses an active schedule or resumes a paused one.

        It only acts on POST. ``update_fields=["ativo"]`` writes just that
        column, without overwriting other fields the task may have updated
        in the meantime (such as ``ultimo_disparo``).

        Args:
            request: HTTP request; requires the
                ``scheduler.change_agendamento`` permission.
            pk: primary key of the schedule.

        Returns:
            Always redirects to the schedule list.
    """
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("robo"), pk=pk
    )

    if request.method == "POST":
        agendamento.ativo = not agendamento.ativo
        agendamento.save(update_fields=["ativo"])
        acao = "retomado" if agendamento.ativo else "pausado"
        messages.success(
            request, f"Agendamento de '{agendamento.robo.nome}' {acao}."
        )

    return redirect("schedule_list")


@permission_required("scheduler.delete_agendamento", raise_exception=True)
def schedule_delete(request, pk):
    """Confirma (GET) e exclui (POST) um agendamento.

    As execuções criadas por ele continuam no histórico: o campo
    ``Execucao.agendamento`` usa ``SET_NULL`` e só perde a referência.

    Args:
        request: requisição HTTP; exige a permissão
            ``scheduler.delete_agendamento``.
        pk: chave primária do agendamento.

    Returns:
        Redireciona para a lista após o POST, ou renderiza a confirmação.

    English:
        Confirms (GET) and deletes (POST) a schedule.

        Executions it created stay in the history: the
        ``Execucao.agendamento`` field uses ``SET_NULL`` and just loses the
        reference.

        Args:
            request: HTTP request; requires the
                ``scheduler.delete_agendamento`` permission.
            pk: primary key of the schedule.

        Returns:
            Redirects to the list after POST, or renders the confirmation.
    """
    agendamento = get_object_or_404(
        Agendamento.objects.select_related("robo"), pk=pk
    )

    if request.method == "POST":
        agendamento.delete()
        messages.success(
            request, f"Agendamento de '{agendamento.robo.nome}' excluído."
        )
        return redirect("schedule_list")

    return render(
        request,
        "scheduler/delete_confirm.html",
        {"agendamento": agendamento},
    )
