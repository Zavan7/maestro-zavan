"""Views de cadastro de agentes, na aba de configurações.

Todas exigem login e ``config.gerenciar_agentes``. O token aparece só
na resposta da criação ou da troca de token, renderizada direto (sem
redirecionar), e não fica em lugar nenhum: nem no banco, nem na sessão,
nem nas mensagens.

English:
    Agent registration views, in the settings tab.

    All require login and ``config.gerenciar_agentes``. The token only
    shows up in the response to creating or replacing it, rendered
    directly (no redirect), and is kept nowhere: not in the database, the
    session or the messages.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.tipos import RequisicaoAutenticada
from agents.forms import AgenteForm
from agents.models import Agente
from agents.services import alternar_agente, criar_agente, gerar_novo_token

PERMISSAO = "config.gerenciar_agentes"


@dataclass(frozen=True, slots=True)
class LinhaAgente:
    """Um agente e o estado calculado para a lista.

    English:
        An agent and the state computed for the list.
    """

    agente: Agente
    estado: str
    texto_estado: str
    total_robos: int


def _renderizar_lista(
    request: RequisicaoAutenticada, form: AgenteForm | None = None
) -> HttpResponse:
    """Renderiza a lista de agentes com o formulário de cadastro.

    Args:
        request: requisição HTTP com ``config.gerenciar_agentes``.
        form: formulário com erros, ou ``None`` para um vazio.

    Returns:
        A página ``config/agentes.html`` renderizada.

    English:
        Renders the agent list with the sign-up form.

        Args:
            request: HTTP request with ``config.gerenciar_agentes``.
            form: form with errors, or ``None`` for an empty one.

        Returns:
            The rendered ``config/agentes.html`` page.
    """
    agora = timezone.now()
    linhas = []
    for agente in Agente.objects.annotate(total_robos=Count("robos")):
        if not agente.ativo:
            estado, texto = "parado", "desativado"
        elif agente.online(agora):
            estado, texto = "rodando", "online"
        else:
            estado, texto = "pausado", "offline"
        linhas.append(LinhaAgente(agente, estado, texto, agente.total_robos))
    return render(
        request,
        "config/agentes.html",
        {"linhas": linhas, "form": form or AgenteForm()},
    )


def _mostrar_token(
    request: RequisicaoAutenticada, agente: Agente, token: str
) -> HttpResponse:
    """Mostra o token recém-gerado, proibindo o navegador de guardar a página.

    ``Cache-Control: no-store`` evita que o token reapareça pelo botão
    "voltar" ou fique no cache do navegador.

    Args:
        request: requisição HTTP.
        agente: agente dono do token.
        token: token em texto, mostrado só aqui.

    Returns:
        A página ``config/agente_token.html``, sem cache.

    English:
        Shows the freshly generated token, forbidding the browser from
        keeping the page.

        ``Cache-Control: no-store`` keeps the token from reappearing
        through the "back" button or staying in the browser cache.

        Args:
            request: HTTP request.
            agente: agent that owns the token.
            token: plain token, shown only here.

        Returns:
            The ``config/agente_token.html`` page, without cache.
    """
    endereco = request.build_absolute_uri("/ws/agente/")
    endereco = endereco.replace("https://", "wss://").replace(
        "http://", "ws://"
    )
    resposta = render(
        request,
        "config/agente_token.html",
        {"agente": agente, "token": token, "endereco": endereco},
    )
    resposta["Cache-Control"] = "no-store"
    return resposta


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def agent_list(request: RequisicaoAutenticada) -> HttpResponse:
    """Lista os agentes, com estado, último sinal e robôs de cada um.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_agentes``.

    Returns:
        A página ``config/agentes.html`` renderizada.

    English:
        Lists the agents, with each one's state, last signal and robots.

        Args:
            request: HTTP request; requires ``config.gerenciar_agentes``.

        Returns:
            The rendered ``config/agentes.html`` page.
    """
    return _renderizar_lista(request)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def agent_create(request: RequisicaoAutenticada) -> HttpResponse:
    """Cria um agente e mostra o token uma única vez.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_agentes``.

    Returns:
        A página do token, a lista com os erros, ou o redirecionamento
        para a lista num GET.

    English:
        Creates an agent and shows the token only once.

        Args:
            request: HTTP request; requires ``config.gerenciar_agentes``.

        Returns:
            The token page, the list with errors, or a redirect to the list
            on GET.
    """
    if request.method != "POST":
        return redirect("agent_list")
    form = AgenteForm(request.POST)
    if not form.is_valid():
        return _renderizar_lista(request, form)
    agente, token = criar_agente(request.user, form.cleaned_data["nome"])
    return _mostrar_token(request, agente, token)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def agent_new_token(request: RequisicaoAutenticada, pk: int) -> HttpResponse:
    """Troca o token do agente e mostra o novo uma única vez.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_agentes``.
        pk: chave primária do agente.

    Returns:
        A página do token, ou o redirecionamento para a lista num GET.

    English:
        Replaces the agent's token and shows the new one only once.

        Args:
            request: HTTP request; requires ``config.gerenciar_agentes``.
            pk: primary key of the agent.

        Returns:
            The token page, or a redirect to the list on GET.
    """
    agente = get_object_or_404(Agente, pk=pk)
    if request.method != "POST":
        return redirect("agent_list")
    token = gerar_novo_token(request.user, agente)
    return _mostrar_token(request, agente, token)


@login_required
@permission_required(PERMISSAO, raise_exception=True)
def agent_toggle(request: RequisicaoAutenticada, pk: int) -> HttpResponse:
    """Desativa ou reativa um agente.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_agentes``.
        pk: chave primária do agente.

    Returns:
        Sempre redireciona para a lista de agentes.

    English:
        Deactivates or reactivates an agent.

        Args:
            request: HTTP request; requires ``config.gerenciar_agentes``.
            pk: primary key of the agent.

        Returns:
            Always redirects to the agent list.
    """
    agente = get_object_or_404(Agente, pk=pk)
    if request.method == "POST":
        alternar_agente(request.user, agente)
        acao = "reativado" if agente.ativo else "desativado"
        messages.success(request, f"Agente '{agente.nome}' {acao}.")
    return redirect("agent_list")
