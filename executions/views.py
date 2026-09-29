from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from executions.models import Execucao


@login_required
def execution_list(request):
    execucoes = Execucao.objects.select_related(
        "robo", "disparado_por", "agendamento__criado_por"
    ).order_by("-id")
    return render(request, "executions/list.html", {"execucoes": execucoes})


@login_required
def execution_detail(request, pk):
    execucao = get_object_or_404(
        Execucao.objects.select_related("robo", "disparado_por", "agendamento__criado_por"),
        pk=pk,
    )
    return render(request, "executions/detail.html", {"execucao": execucao})
