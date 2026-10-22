"""Views do app de execuções.

English:
    Views for the executions app.
"""

from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

from accounts.tipos import RequisicaoAutenticada
from executions.ao_vivo import numerar_log
from executions.models import Execucao


@login_required
@permission_required("executions.view_execucao", raise_exception=True)
def execution_list(request: RequisicaoAutenticada) -> HttpResponse:
    """Lista todas as execuções, das mais recentes para as mais antigas.

    O ``select_related`` traz junto o robô, quem disparou e o criador do
    agendamento (``agendamento__criado_por`` segue duas relações). Sem
    ele, cada linha da tabela faria consultas extras (problema N+1).

    Args:
        request: requisição HTTP do usuário logado.

    Returns:
        A página ``executions/list.html`` renderizada.

    English:
        Lists every execution, newest first.

        ``select_related`` fetches the robot, who triggered it and the
        schedule's creator in the same query (``agendamento__criado_por``
        follows two relations). Without it, each table row would run extra
        queries (the N+1 problem).

        Args:
            request: HTTP request from the logged-in user.

        Returns:
            The rendered ``executions/list.html`` page.
    """
    execucoes = Execucao.objects.select_related(
        "robo", "disparado_por", "agendamento__criado_por"
    ).order_by("-id")
    return render(request, "executions/list.html", {"execucoes": execucoes})


@login_required
@permission_required("executions.view_execucao", raise_exception=True)
def execution_detail(request: RequisicaoAutenticada, pk: int) -> HttpResponse:
    """Mostra uma execução com o log, ao vivo enquanto ela roda.

    ``get_object_or_404`` aceita um QuerySet, e não só o model: assim dá
    para usar ``select_related`` e ainda responder 404 quando o id não
    existe.

    O log guardado pode ter perdido o começo (só o fim cabe no limite).
    ``numerar_log`` devolve as linhas com o número certo, a lista começa
    no número da primeira, e as linhas que chegam pelo WebSocket
    continuam essa numeração.

    Args:
        request: requisição HTTP do usuário logado.
        pk: chave primária da execução.

    Returns:
        A página ``executions/detail.html`` renderizada.

    English:
        Shows one execution with its log, live while it runs.

        ``get_object_or_404`` accepts a QuerySet, not only the model: that
        way we can use ``select_related`` and still answer 404 when the id
        does not exist.

        The stored log may have lost its start (only the end fits in the
        limit). ``numerar_log`` returns the lines with the right numbers,
        the list starts at the first one's number, and the lines arriving
        through the WebSocket continue that numbering.

        Args:
            request: HTTP request from the logged-in user.
            pk: primary key of the execution.

        Returns:
            The rendered ``executions/detail.html`` page.
    """
    execucao = get_object_or_404(
        Execucao.objects.select_related(
            "robo__agente", "disparado_por", "agendamento__criado_por"
        ),
        pk=pk,
    )
    linhas = numerar_log(execucao.log, execucao.total_linhas)
    contexto = {
        "execucao": execucao,
        "linhas": [linha["texto"] for linha in linhas],
        "primeira_linha": linhas[0]["numero"] if linhas else 1,
        "ultima_linha": linhas[-1]["numero"] if linhas else 0,
        "ao_vivo": execucao.status
        in (Execucao.Status.PENDENTE, Execucao.Status.RODANDO),
    }
    return render(request, "executions/detail.html", contexto)
