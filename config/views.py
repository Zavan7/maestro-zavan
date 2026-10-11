"""Views da aba de configurações e da gestão de usuários.

English:
    Views for the settings tab and user management.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from config.models import ConfiguracaoSistema, RegistroAcesso
from config.services import (
    AlteracaoRecusada,
    alternar_ativo,
    pode_alterar,
    trocar_grupo,
)
from robots.tasks import LIMITE_LOG, TIMEOUT_SEGUNDOS

User = get_user_model()


def exige_acesso_a_configuracoes(view):
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
    def embrulho(request, *args, **kwargs):
        if not request.user.has_module_perms("config"):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return embrulho


@exige_acesso_a_configuracoes
def config_home(request):
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
    contexto = {
        "configuracao": ConfiguracaoSistema.atual(),
        "timeout_padrao": TIMEOUT_SEGUNDOS,
        "limite_log": LIMITE_LOG,
        "usuarios_ativos": User.objects.filter(is_active=True).count(),
        "usuarios_inativos": User.objects.filter(is_active=False).count(),
    }
    return render(request, "config/home.html", contexto)


@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_users(request):
    """Lista os usuários com o grupo atual e o registro de acesso recente.

    ``prefetch_related("groups")`` busca os grupos de todos os usuários de
    uma vez. Para cada usuário, a view guarda o grupo atual e se ele pode
    ser editado por quem está logado (``pode_alterar``).

    Args:
        request: requisição HTTP; exige ``config.gerenciar_usuarios``.

    Returns:
        A página ``config/usuarios.html`` renderizada.

    English:
        Lists users with their current group and the recent access log.

        ``prefetch_related("groups")`` fetches every user's groups at once.
        For each user, the view stores the current group and whether the
        logged-in user may edit them (``pode_alterar``).

        Args:
            request: HTTP request; requires ``config.gerenciar_usuarios``.

        Returns:
            The rendered ``config/usuarios.html`` page.
    """
    usuarios = list(
        User.objects.prefetch_related("groups").order_by(
            "-is_active", "username"
        )
    )
    for usuario in usuarios:
        grupos = list(usuario.groups.all())
        usuario.grupo_atual = grupos[0] if grupos else None
        usuario.editavel = pode_alterar(request.user, usuario)

    contexto = {
        "usuarios": usuarios,
        "grupos": Group.objects.order_by("name"),
        "registros": RegistroAcesso.objects.select_related("autor")[:15],
    }
    return render(request, "config/usuarios.html", contexto)


@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_user_group(request, pk):
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


@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_user_toggle(request, pk):
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
