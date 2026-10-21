"""Views da aba de configurações e da gestão de usuários.

As views de cada seção usam ``@login_required`` antes de
``@permission_required(..., raise_exception=True)``. Sozinho, o segundo
responde 403 também para quem não está logado; com o primeiro na frente,
o visitante vai para o login e só o usuário logado sem permissão recebe
403.

English:
    Views for the settings tab and user management.

    Each section's views use ``@login_required`` before
    ``@permission_required(..., raise_exception=True)``. On its own, the
    latter answers 403 even to visitors who are not logged in; with the
    former in front, visitors go to the login page and only a logged-in
    user without permission gets 403.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.tipos import RequisicaoAutenticada
from config.forms import NovoUsuarioForm, RetencaoForm
from config.models import ConfiguracaoSistema, RegistroAcesso
from config.services import (
    AlteracaoRecusada,
    alternar_ativo,
    criar_usuario,
    limite_da_retencao,
    pode_alterar,
    trocar_grupo,
)
from config.status import status_do_sistema
from robots.tasks import LIMITE_LOG, TIMEOUT_SEGUNDOS

View = Callable[..., HttpResponse]


@dataclass(frozen=True, slots=True)
class LinhaUsuario:
    """Um usuário e o que a tela de usuários precisa saber sobre ele.

    English:
        A user and what the users page needs to know about them.
    """

    usuario: User
    grupo_atual: Group | None
    editavel: bool


def exige_acesso_a_configuracoes(view: View) -> View:
    """Decorator que exige login e alguma permissão do app ``config``.

    Um decorator é uma função que "embrulha" outra para acrescentar
    comportamento antes dela. Aqui:

    - ``@login_required`` manda quem não está logado para o login;
    - ``has_module_perms("config")`` é verdadeiro se o usuário tem
      qualquer permissão do app; se não tiver, ``PermissionDenied`` faz o
      Django responder 403;
    - ``@wraps(view)`` preserva o nome e a docstring da view original.

    Args:
        view: a view a ser protegida.

    Returns:
        A view embrulhada, com as verificações de acesso.

    English:
        Decorator that requires login and any permission of the ``config``
        app.

        A decorator is a function that "wraps" another one to add behavior
        before it. Here:

        - ``@login_required`` sends anyone not logged in to the login page;
        - ``has_module_perms("config")`` is true if the user has any
          permission in the app; if not, ``PermissionDenied`` makes Django
          answer 403;
        - ``@wraps(view)`` keeps the original view's name and docstring.

        Args:
            view: the view to protect.

        Returns:
            The wrapped view, with the access checks.
    """

    @login_required
    @wraps(view)
    def embrulho(
        request: RequisicaoAutenticada, *args: Any, **kwargs: Any
    ) -> HttpResponse:
        if not request.user.has_module_perms("config"):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return embrulho


def _renderizar_home(
    request: RequisicaoAutenticada, form_retencao: RetencaoForm | None = None
) -> HttpResponse:
    """Monta o contexto da aba de configurações e renderiza a página.

    Usada pela própria aba e pela view de retenção, que precisa
    reexibir a página com os erros do formulário. O status do sistema só é
    verificado para quem pode vê-lo, porque cada verificação conversa com
    o Redis e com o worker e leva algum tempo.

    Args:
        request: requisição HTTP de um usuário com acesso à aba.
        form_retencao: formulário de retenção com erros, ou ``None`` para
            um formulário novo com o valor atual.

    Returns:
        A página ``config/home.html`` renderizada.

    English:
        Builds the settings tab context and renders the page.

        Used by the tab itself and by the retention view, which needs to
        show the page again with the form errors. The system status is
        only checked for users allowed to see it, because each check talks
        to Redis and to the worker and takes some time.

        Args:
            request: HTTP request from a user with access to the tab.
            form_retencao: retention form with errors, or ``None`` for a
                fresh form with the current value.

        Returns:
            The rendered ``config/home.html`` page.
    """
    configuracao = ConfiguracaoSistema.atual()
    pode_ver_status = request.user.has_perm("config.ver_status_sistema")
    contexto = {
        "configuracao": configuracao,
        "form_retencao": form_retencao or RetencaoForm(instance=configuracao),
        "limite_retencao": limite_da_retencao(),
        "status_sistema": status_do_sistema() if pode_ver_status else [],
        "timeout_padrao": TIMEOUT_SEGUNDOS,
        "limite_log": LIMITE_LOG,
        "usuarios_ativos": User.objects.filter(is_active=True).count(),
        "usuarios_inativos": User.objects.filter(is_active=False).count(),
    }
    return render(request, "config/home.html", contexto)


@exige_acesso_a_configuracoes
def config_home(request: RequisicaoAutenticada) -> HttpResponse:
    """Exibe a aba de configurações.

    Cada seção aparece de acordo com a permissão do usuário; quem decide
    isso é o template, com ``perms``. Os limites de execução vêm das
    constantes de ``robots.tasks``, para a tela mostrar sempre os valores
    reais.

    Args:
        request: requisição HTTP de um usuário com acesso à aba.

    Returns:
        A página ``config/home.html`` renderizada.

    English:
        Shows the settings tab.

        Each section appears according to the user's permissions; the
        template decides that with ``perms``. The execution limits come
        from the ``robots.tasks`` constants, so the page always shows the
        real values.

        Args:
            request: HTTP request from a user with access to the tab.

        Returns:
            The rendered ``config/home.html`` page.
    """
    return _renderizar_home(request)


@login_required
@permission_required("config.gerenciar_retencao", raise_exception=True)
def config_retention(request: RequisicaoAutenticada) -> HttpResponse:
    """Salva o novo prazo de retenção do histórico.

    Só age em POST; um GET volta para a aba sem alterar nada. Com um
    valor fora dos limites, a aba é exibida de novo com o erro do campo.
    A limpeza em si não acontece aqui: ela roda de madrugada, pelo beat.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_retencao``.

    Returns:
        Redireciona para a aba após salvar, ou a renderiza com os erros.

    English:
        Saves the new history retention period.

        It only acts on POST; a GET goes back to the tab, changing
        nothing. With a value out of bounds, the tab is shown again with
        the field error. The cleanup itself does not happen here: it runs
        overnight, through beat.

        Args:
            request: HTTP request; requires ``config.gerenciar_retencao``.

        Returns:
            Redirects to the tab after saving, or renders it with errors.
    """
    if request.method != "POST":
        return redirect("config_home")

    form = RetencaoForm(request.POST, instance=ConfiguracaoSistema.atual())
    if not form.is_valid():
        messages.error(request, "Retenção não salva: confira o valor.")
        return _renderizar_home(request, form_retencao=form)

    configuracao = form.save()
    messages.success(
        request, f"Retenção salva: {configuracao.retencao_dias} dias."
    )
    return redirect("config_home")


@login_required
@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_users(request: RequisicaoAutenticada) -> HttpResponse:
    """Lista os usuários com o grupo atual e o registro de acesso recente.

    ``prefetch_related("groups")`` busca os grupos de todos os usuários de
    uma vez. Para cada usuário, a view monta uma ``LinhaUsuario`` com o
    grupo atual e se ele pode ser editado por quem está logado
    (``pode_alterar``).

    Args:
        request: requisição HTTP; exige ``config.gerenciar_usuarios``.

    Returns:
        A página ``config/usuarios.html`` renderizada.

    English:
        Lists users with their current group and the recent access log.

        ``prefetch_related("groups")`` fetches every user's groups at once.
        For each user, the view builds a ``LinhaUsuario`` with the current
        group and whether the logged-in user may edit them
        (``pode_alterar``).

        Args:
            request: HTTP request; requires ``config.gerenciar_usuarios``.

        Returns:
            The rendered ``config/usuarios.html`` page.
    """
    usuarios = User.objects.prefetch_related("groups").order_by(
        "-is_active", "username"
    )
    linhas = [
        LinhaUsuario(
            usuario=usuario,
            grupo_atual=next(iter(usuario.groups.all()), None),
            editavel=pode_alterar(request.user, usuario),
        )
        for usuario in usuarios
    ]

    contexto = {
        "linhas": linhas,
        "grupos": Group.objects.order_by("name"),
        "registros": RegistroAcesso.objects.select_related("autor")[:15],
    }
    return render(request, "config/usuarios.html", contexto)


@login_required
@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_user_group(request: RequisicaoAutenticada, pk: int) -> HttpResponse:
    """Troca o grupo de um usuário.

    Só age em POST. Um grupo vazio no formulário significa "sem grupo";
    um id de grupo inexistente responde 404. A recusa das travas vira
    ``messages.error``.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_usuarios``.
        pk: chave primária do usuário alvo.

    Returns:
        Sempre redireciona para a lista de usuários.

    English:
        Changes a user's group.

        It only acts on POST. An empty group in the form means "no group";
        a nonexistent group id answers 404. A refusal from the safeguards
        becomes ``messages.error``.

        Args:
            request: HTTP request; requires ``config.gerenciar_usuarios``.
            pk: primary key of the target user.

        Returns:
            Always redirects to the user list.
    """
    alvo = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        grupo_id = request.POST.get("grupo")
        grupo = get_object_or_404(Group, pk=grupo_id) if grupo_id else None
        try:
            trocar_grupo(request.user, alvo, grupo)
        except AlteracaoRecusada as erro:
            messages.error(
                request, f"Não é possível alterar '{alvo.username}': {erro}."
            )
        else:
            messages.success(request, f"Grupo de '{alvo.username}' alterado.")

    return redirect("config_users")


@login_required
@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_user_toggle(
    request: RequisicaoAutenticada, pk: int
) -> HttpResponse:
    """Desativa ou reativa um usuário.

    Só age em POST; um GET apenas redireciona, sem alterar nada.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_usuarios``.
        pk: chave primária do usuário alvo.

    Returns:
        Sempre redireciona para a lista de usuários.

    English:
        Deactivates or reactivates a user.

        It only acts on POST; a GET just redirects, changing nothing.

        Args:
            request: HTTP request; requires ``config.gerenciar_usuarios``.
            pk: primary key of the target user.

        Returns:
            Always redirects to the user list.
    """
    alvo = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        try:
            alternar_ativo(request.user, alvo)
        except AlteracaoRecusada as erro:
            messages.error(
                request, f"Não é possível alterar '{alvo.username}': {erro}."
            )
        else:
            acao = "reativado" if alvo.is_active else "desativado"
            messages.success(request, f"Usuário '{alvo.username}' {acao}.")

    return redirect("config_users")


@login_required
@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_user_create(request: RequisicaoAutenticada) -> HttpResponse:
    """Cadastra um usuário comum pela aba, já com o grupo escolhido.

    A gravação e o registro de auditoria ficam em ``criar_usuario``; a
    view só cuida do formulário e da mensagem.

    Args:
        request: requisição HTTP; exige ``config.gerenciar_usuarios``.

    Returns:
        Redireciona para a lista de usuários após criar, ou renderiza o
        formulário (vazio ou com os erros).

    English:
        Creates a regular user through the tab, with the chosen group.

        Saving and the audit record live in ``criar_usuario``; the view
        only handles the form and the message.

        Args:
            request: HTTP request; requires ``config.gerenciar_usuarios``.

        Returns:
            Redirects to the user list after creating, or renders the form
            (empty or with errors).
    """
    if request.method == "POST":
        form = NovoUsuarioForm(request.POST)
        if form.is_valid():
            usuario = criar_usuario(request.user, form)
            messages.success(request, f"Usuário '{usuario.username}' criado.")
            return redirect("config_users")
    else:
        form = NovoUsuarioForm()

    return render(request, "config/usuario_form.html", {"form": form})
