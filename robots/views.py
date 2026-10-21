"""Views do app de robôs: listar, cadastrar, editar, excluir, iniciar e parar.

Todas as ações que alteram dados só agem em POST, e cada uma exige a
permissão certa com ``@permission_required(..., raise_exception=True)``.
Esconder o botão no template é só aparência; a proteção de verdade é
na view.

English:
    Robots app views: list, create, edit, delete, start and stop.

    Every action that changes data only acts on POST, and each one
    requires the right permission with
    ``@permission_required(..., raise_exception=True)``. Hiding the
    button in the template is just cosmetics; the real protection is in
    the view.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Prefetch, ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.tipos import RequisicaoAutenticada
from agents.comandos import mandar_parar
from executions.ao_vivo import publicar_fim
from executions.models import Execucao
from robots.forms import RoboForm
from robots.models import Robo
from robots.services import DisparoRecusado, disparar_execucao
from scheduler.models import formatar_proxima


def _estado_da_agenda(robo, agora):
    """Calcula o estado de agendamento do robô para a listagem.

    As regras são:

    - tem algum agendamento ativo: ``agendado``, com o texto da próxima
      ocorrência (por exemplo, ``hoje 08:00``);
    - tem agendamentos, mas todos pausados: ``pausado``;
    - não tem agendamentos: ``manual``.

    A view calcula o estado e o template só aplica a classe de CSS
    correspondente.

    Args:
        robo: robô com ``agendamentos`` já pré-carregados
            (``prefetch_related``), para não gerar uma consulta por robô.
        agora: momento de referência para a próxima ocorrência.

    Returns:
        Tupla ``(estado, texto)``.

    English:
        Computes the robot's scheduling state for the list page.

        The rules are:

        - it has an active schedule: ``agendado``, with the next run as
          text (e.g. ``hoje 08:00``);
        - it has schedules, but all paused: ``pausado``;
        - it has no schedules: ``manual``.

        The view computes the state and the template only applies the
        matching CSS class.

        Args:
            robo: robot with ``agendamentos`` already prefetched
                (``prefetch_related``), so there is no query per robot.
            agora: reference time for the next run.

        Returns:
            Tuple ``(estado, texto)``.
    """
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
    """Lista os robôs com a última execução e os estados de cada um.

    Para evitar o problema N+1, as execuções e os agendamentos de todos os
    robôs são buscados de uma vez com ``prefetch_related``. O ``Prefetch``
    com ``to_attr`` guarda as execuções, da mais recente para a mais
    antiga, numa lista ``execucoes_recentes`` em cada robô.

    O ``list()`` em volta da consulta protege os atributos que o loop
    adiciona (``estado_agora``, ``estado_agenda``...). Um QuerySet já
    percorrido até guarda os objetos em cache, mas qualquer ``.filter()``
    ou ``.order_by()`` acrescentado depois criaria um QuerySet novo, que
    vai ao banco de novo e devolve objetos sem esses atributos, deixando
    células vazias sem nenhum erro. Com a lista, isso não acontece.

    Args:
        request: requisição HTTP do usuário logado.

    Returns:
        A página ``robots/list.html`` renderizada.

    English:
        Lists robots with their latest execution and current states.

        To avoid the N+1 problem, the executions and schedules of all
        robots are fetched at once with ``prefetch_related``. The
        ``Prefetch`` with ``to_attr`` stores the executions, newest first,
        in an ``execucoes_recentes`` list on each robot.

        The ``list()`` around the query protects the attributes the loop
        adds (``estado_agora``, ``estado_agenda``...). An already
        iterated QuerySet does cache its objects, but any ``.filter()``
        or ``.order_by()`` added later would create a new QuerySet that
        hits the database again and returns objects without those
        attributes, leaving empty cells with no error at all. With a
        list, that cannot happen.

        Args:
            request: HTTP request from the logged-in user.

        Returns:
            The rendered ``robots/list.html`` page.
    """
    robos = list(
        Robo.objects.select_related("agente")
        .prefetch_related(
            Prefetch(
                "execucoes",
                queryset=Execucao.objects.order_by("-id"),
                to_attr="execucoes_recentes",
            ),
            "agendamentos",
        )
        .order_by("nome")
    )

    agora = timezone.localtime()
    for robo in robos:
        ultima = (
            robo.execucoes_recentes[0] if robo.execucoes_recentes else None
        )
        robo.ultima_execucao = ultima

        if ultima and ultima.status == Execucao.Status.RODANDO:
            texto = "parando" if ultima.parada_solicitada else "rodando"
            robo.estado_agora, robo.texto_agora = "rodando", texto
        elif ultima and ultima.status == Execucao.Status.PENDENTE:
            robo.estado_agora, robo.texto_agora = "rodando", "aguardando"
        else:
            robo.estado_agora, robo.texto_agora = "parado", "parado"

        robo.estado_agenda, robo.texto_agenda = _estado_da_agenda(robo, agora)
        robo.agenda_bloqueada = (
            robo.estado_agenda == "agendado"
            and robo.status != Robo.Status.ATIVO
        )

    return render(request, "robots/list.html", {"robos": robos})


@permission_required("robots.add_robo", raise_exception=True)
def robot_create(request):
    """Cadastra um novo robô.

    No GET mostra o formulário vazio. No POST valida os dados; se estiverem
    certos, salva com ``commit=False`` para preencher o ``responsavel`` com
    o usuário logado antes de gravar. Se houver erro, o formulário volta
    com as mensagens de validação.

    Args:
        request: requisição HTTP; exige a permissão ``robots.add_robo``.

    Returns:
        Redireciona para a lista após salvar, ou renderiza o formulário.

    English:
        Creates a new robot.

        On GET it shows the empty form. On POST it validates the data; if
        valid, it saves with ``commit=False`` to fill ``responsavel`` with
        the logged-in user before writing. On errors, the form comes back
        with the validation messages.

        Args:
            request: HTTP request; requires the ``robots.add_robo``
                permission.

        Returns:
            Redirects to the list after saving, or renders the form.
    """
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
    """Edita os dados de um robô existente.

    ``get_object_or_404`` responde 404 se o robô não existir, em vez de
    estourar um erro 500. Passar ``instance=robo`` ao formulário faz ele
    vir preenchido no GET e atualizar o mesmo registro no POST.

    Args:
        request: requisição HTTP; exige a permissão ``robots.change_robo``.
        pk: chave primária do robô.

    Returns:
        Redireciona para a lista após salvar, ou renderiza o formulário.

    English:
        Edits an existing robot.

        ``get_object_or_404`` answers 404 if the robot does not exist,
        instead of raising a 500 error. Passing ``instance=robo`` to the
        form fills it in on GET and updates the same record on POST.

        Args:
            request: HTTP request; requires the ``robots.change_robo``
                permission.
            pk: primary key of the robot.

        Returns:
            Redirects to the list after saving, or renders the form.
    """
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
    """Confirma (GET) e exclui (POST) um robô.

    O GET mostra uma página de confirmação; só o POST exclui de fato. Se o
    robô tiver execuções, o ``on_delete=PROTECT`` de ``Execucao.robo``
    levanta ``ProtectedError``: em vez de quebrar, a view mostra uma
    mensagem explicando o motivo e preserva o histórico.

    Args:
        request: requisição HTTP; exige a permissão ``robots.delete_robo``.
        pk: chave primária do robô.

    Returns:
        Redireciona para a lista após o POST, ou renderiza a confirmação.

    English:
        Confirms (GET) and deletes (POST) a robot.

        GET shows a confirmation page; only POST actually deletes. If the
        robot has executions, the ``on_delete=PROTECT`` on
        ``Execucao.robo`` raises ``ProtectedError``: instead of crashing,
        the view shows a message explaining why and keeps the history.

        Args:
            request: HTTP request; requires the ``robots.delete_robo``
                permission.
            pk: primary key of the robot.

        Returns:
            Redirects to the list after POST, or renders the confirmation.
    """
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        try:
            robo.delete()
        except ProtectedError:
            messages.error(
                request,
                f"Não é possível excluir '{robo.nome}': "
                "existem execuções associadas a ele.",
            )
            return redirect("robot_list")

        messages.success(request, f"Robô '{robo.nome}' excluído.")
        return redirect("robot_list")

    return render(request, "robots/exclusion_confirm.html", {"robo": robo})


@permission_required("robots.executar_robo", raise_exception=True)
def robot_start(request, pk):
    """Dispara uma execução manual do robô.

    Só age em POST. A regra de negócio fica toda em
    ``disparar_execucao``; a view apenas traduz o resultado em mensagem:
    ``DisparoRecusado`` vira ``messages.error`` e o sucesso vira
    ``messages.success``.

    Args:
        request: requisição HTTP; exige a permissão
            ``robots.executar_robo``.
        pk: chave primária do robô.

    Returns:
        Sempre redireciona para a lista de robôs.

    English:
        Triggers a manual execution of the robot.

        It only acts on POST. The business rule lives entirely in
        ``disparar_execucao``; the view just turns the outcome into a
        message: ``DisparoRecusado`` becomes ``messages.error`` and success
        becomes ``messages.success``.

        Args:
            request: HTTP request; requires the ``robots.executar_robo``
                permission.
            pk: primary key of the robot.

        Returns:
            Always redirects to the robot list.
    """
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        try:
            disparar_execucao(robo, disparado_por=request.user)
        except DisparoRecusado as erro:
            messages.error(
                request, f"Não é possível iniciar '{robo.nome}': {erro}."
            )
        else:
            messages.success(request, f"Execução de '{robo.nome}' iniciada.")

    return redirect("robot_list")


def _cancelar(execucao: Execucao, motivo: str) -> None:
    """Encerra a execução como cancelada, no registro, e avisa a tela.

    Usado quando não há processo para parar: a execução ainda estava na
    fila, ou o agente que a rodava saiu do ar.

    Args:
        execucao: execução pendente ou rodando.
        motivo: frase que vai para o log, explicando o cancelamento.

    English:
        Ends the execution as cancelled, in the record, and notifies the
        page.

        Used when there is no process to stop: the execution was still
        queued, or the agent running it went offline.

        Args:
            execucao: pending or running execution.
            motivo: sentence that goes into the log, explaining why.
    """
    execucao.status = Execucao.Status.CANCELADA
    execucao.finalizado_em = timezone.now()
    execucao.log = "\n".join(filter(None, [execucao.log, motivo]))
    execucao.save(update_fields=["status", "finalizado_em", "log"])
    publicar_fim(execucao.pk, execucao.status)


@permission_required("robots.executar_robo", raise_exception=True)
def robot_stop(request: RequisicaoAutenticada, pk: int) -> HttpResponse:
    """Para a execução em andamento do robô.

    - Execução ``PENDENTE`` (ainda na fila, por exemplo com o worker
      parado) é cancelada na hora. Como o worker e o agente só rodam o
      script se a execução ainda estiver pendente, ela não roda depois.
    - Execução ``RODANDO`` recebe ``parada_solicitada``. No worker, o
      executor confere esse campo a cada segundo; num agente, o comando
      ``parar`` vai junto. Quem marca ``CANCELADA`` é quem roda o robô,
      quando o processo de fato terminou; por isso a mensagem diz
      "parada solicitada", e não "parada".
    - Execução ``RODANDO`` num agente que está offline é cancelada na
      hora: não há quem receba o pedido, e o robô ficaria travado.

    O ``update()`` grava só o campo do pedido, sem sobrescrever o que o
    worker estiver gravando na mesma execução.

    Args:
        request: requisição HTTP; exige a permissão
            ``robots.executar_robo``.
        pk: chave primária do robô.

    Returns:
        Sempre redireciona para a lista de robôs.

    English:
        Stops the robot's execution in progress.

        - A ``PENDENTE`` execution (still queued, e.g. with the worker
          down) is cancelled right away. Since the worker and the agent
          only run the script if the execution is still pending, it does
          not run later.
        - A ``RODANDO`` execution gets ``parada_solicitada``. In the
          worker, the executor checks that field every second; on an
          agent, the ``parar`` command goes along. Whoever runs the robot
          sets ``CANCELADA``, once the process has really ended; that is
          why the message says "stop requested", not "stopped".
        - A ``RODANDO`` execution on an agent that is offline is cancelled
          right away: nobody would get the request, and the robot would be
          stuck.

        ``update()`` writes only the request field, without overwriting
        what the worker may be saving on the same execution.

        Args:
            request: HTTP request; requires the ``robots.executar_robo``
                permission.
            pk: primary key of the robot.

        Returns:
            Always redirects to the robot list.
    """
    robo = get_object_or_404(Robo.objects.select_related("agente"), pk=pk)

    if request.method != "POST":
        return redirect("robot_list")

    execucao = robo.execucoes.filter(
        status__in=[Execucao.Status.PENDENTE, Execucao.Status.RODANDO]
    ).last()
    agente = robo.agente
    if execucao is None:
        messages.error(
            request, f"'{robo.nome}' não tem execução em andamento."
        )
        return redirect("robot_list")

    if agente is not None:
        mandar_parar(agente.pk, execucao.pk)

    if execucao.status == Execucao.Status.PENDENTE:
        _cancelar(
            execucao,
            f"Cancelada antes de iniciar por {request.user.username}.",
        )
        messages.success(
            request, f"Execução pendente de '{robo.nome}' cancelada."
        )
    elif agente is not None and not agente.online():
        _cancelar(
            execucao,
            f"Cancelada por {request.user.username}: o agente "
            f"'{agente.nome}' está offline.",
        )
        messages.success(
            request,
            f"Execução de '{robo.nome}' cancelada: o agente está offline.",
        )
    else:
        Execucao.objects.filter(pk=execucao.pk).update(parada_solicitada=True)
        messages.success(
            request,
            f"Parada de '{robo.nome}' solicitada; o robô para em instantes.",
        )

    return redirect("robot_list")

    execucao = robo.execucoes.filter(
        status__in=[Execucao.Status.PENDENTE, Execucao.Status.RODANDO]
    ).last()
    if execucao is None:
        messages.error(
            request, f"'{robo.nome}' não tem execução em andamento."
        )
    elif execucao.status == Execucao.Status.PENDENTE:
        execucao.status = Execucao.Status.CANCELADA
        execucao.finalizado_em = timezone.now()
        execucao.log = (
            f"Cancelada antes de iniciar por {request.user.username}."
        )
        execucao.save(update_fields=["status", "finalizado_em", "log"])
        publicar_fim(execucao.pk, execucao.status)
        messages.success(
            request, f"Execução pendente de '{robo.nome}' cancelada."
        )
    else:
        Execucao.objects.filter(pk=execucao.pk).update(parada_solicitada=True)
        messages.success(
            request,
            f"Parada de '{robo.nome}' solicitada; o robô para em instantes.",
        )

    return redirect("robot_list")
