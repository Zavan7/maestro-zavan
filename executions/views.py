"""Views do app de execuções.

English:
    Views for the executions app.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from executions.models import Execucao


@login_required
def execution_list(request):
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
def execution_detail(request, pk):
    """Mostra uma execução com o log completo.

    ``get_object_or_404`` aceita um QuerySet, e não só o model: assim dá
    para usar ``select_related`` e ainda responder 404 quando o id não
    existe.

    Args:
        request: requisição HTTP do usuário logado.
        pk: chave primária da execução.

    Returns:
        A página ``executions/detail.html`` renderizada.

    English:
        Shows one execution with its full log.

        ``get_object_or_404`` accepts a QuerySet, not only the model: that
        way we can use ``select_related`` and still answer 404 when the id
        does not exist.

        Args:
            request: HTTP request from the logged-in user.
            pk: primary key of the execution.

        Returns:
            The rendered ``executions/detail.html`` page.
    """
    execucao = get_object_or_404(
        Execucao.objects.select_related(
            "robo", "disparado_por", "agendamento__criado_por"
        ),
        pk=pk,
    )
    return render(request, "executions/detail.html", {"execucao": execucao})
