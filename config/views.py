from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from config.models import ConfiguracaoSistema, RegistroAcesso
from config.services import AlteracaoRecusada, alternar_ativo, pode_alterar, trocar_grupo
from robots.tasks import LIMITE_LOG, TIMEOUT_SEGUNDOS

User = get_user_model()


def exige_acesso_a_configuracoes(view):
    @login_required
    @wraps(view)
    def embrulho(request, *args, **kwargs):
        if not request.user.has_module_perms("config"):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return embrulho


@exige_acesso_a_configuracoes
def config_home(request):
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
    usuarios = list(User.objects.prefetch_related("groups").order_by("-is_active", "username"))
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
    alvo = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        grupo_id = request.POST.get("grupo")
        grupo = get_object_or_404(Group, pk=grupo_id) if grupo_id else None
        try:
            trocar_grupo(request.user, alvo, grupo)
        except AlteracaoRecusada as erro:
            messages.error(request, f"Não é possível alterar '{alvo.username}': {erro}.")
        else:
            messages.success(request, f"Grupo de '{alvo.username}' alterado.")

    return redirect("config_users")


@permission_required("config.gerenciar_usuarios", raise_exception=True)
def config_user_toggle(request, pk):
    alvo = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        try:
            alternar_ativo(request.user, alvo)
        except AlteracaoRecusada as erro:
            messages.error(request, f"Não é possível alterar '{alvo.username}': {erro}.")
        else:
            acao = "reativado" if alvo.is_active else "desativado"
            messages.success(request, f"Usuário '{alvo.username}' {acao}.")

    return redirect("config_users")
