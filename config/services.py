"""Serviços da aba de configurações: gestão de acesso e retenção.

As regras ficam aqui, longe das views, para valerem em qualquer lugar
que altere acesso. As funções que alteram dados usam
``@transaction.atomic``: ou a alteração e o registro de auditoria são
gravados juntos, ou nada é gravado.

English:
    Settings tab services: access management and retention.

    The rules live here, away from the views, so they apply anywhere
    access is changed. Functions that change data use
    ``@transaction.atomic``: either the change and its audit record are
    saved together, or nothing is saved.
"""

from datetime import datetime, timedelta

from django.contrib.auth.models import Group, User
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from config.forms import NovoUsuarioForm
from config.models import ConfiguracaoSistema, RegistroAcesso
from executions.models import Execucao

STATUS_FINALIZADOS = [
    Execucao.Status.SUCESSO,
    Execucao.Status.FALHA,
    Execucao.Status.CANCELADA,
]


class AlteracaoRecusada(Exception):
    """Indica que a alteração de acesso não é permitida.

    A mensagem diz o motivo, pronta para aparecer ao usuário.

    English:
        Signals that the access change is not allowed.

        The message states the reason, ready to be shown to the user.
    """


def _verificar_se_pode_alterar(autor: User, alvo: User) -> None:
    """Aplica as travas da gestão de acesso.

    As duas travas evitam acidentes graves:

    - ninguém altera o próprio acesso, para um administrador não se
      trancar do lado de fora sem querer;
    - só um superusuário altera outro superusuário, para um administrador
      comum não conseguir derrubar quem tem acesso total.

    Args:
        autor: usuário que quer fazer a alteração.
        alvo: usuário que seria alterado.

    Raises:
        AlteracaoRecusada: se alguma das travas recusar.

    English:
        Applies the access management safeguards.

        Both safeguards prevent serious accidents:

        - nobody changes their own access, so an administrator cannot lock
          themselves out by mistake;
        - only a superuser can change another superuser, so a regular
          administrator cannot take down someone with full access.

        Args:
            autor: user who wants to make the change.
            alvo: user who would be changed.

        Raises:
            AlteracaoRecusada: if any safeguard refuses.
    """
    if alvo.pk == autor.pk:
        raise AlteracaoRecusada("não é possível alterar o próprio acesso")
    if alvo.is_superuser and not autor.is_superuser:
        raise AlteracaoRecusada(
            "só um superusuário pode alterar outro superusuário"
        )


def grupos_que_pode_conceder(autor: User) -> QuerySet[Group]:
    """Grupos cujas permissões o autor já tem por inteiro.

    Sem esta regra, quem só gerencia usuários conseguiria qualquer
    permissão: bastaria criar uma conta para si num grupo com mais
    poderes (o Administrador do sistema, que não edita robôs, criaria uma
    conta "Administrador RPA"). Superusuário pode conceder todos.

    Args:
        autor: usuário que quer conceder o grupo.

    Returns:
        Os grupos que ele pode conceder, por nome.

    English:
        Groups whose permissions the author already fully holds.

        Without this rule, someone who only manages users could get any
        permission: they would just create an account for themselves in a
        more powerful group (the system administrator, who cannot edit
        robots, would create an "Administrador RPA" account). A superuser
        may grant them all.

        Args:
            autor: user who wants to grant the group.

        Returns:
            The groups they may grant, by name.
    """
    grupos = Group.objects.order_by("name")
    if autor.is_superuser:
        return grupos
    minhas = autor.get_all_permissions()
    permitidos = [
        grupo.pk
        for grupo in grupos.prefetch_related("permissions__content_type")
        if {
            f"{p.content_type.app_label}.{p.codename}"
            for p in grupo.permissions.all()
        }
        <= minhas
    ]
    return grupos.filter(pk__in=permitidos)


def _verificar_grupo(autor: User, grupo: Group | None) -> None:
    """Recusa conceder um grupo com permissões que o autor não tem.

    Args:
        autor: usuário que quer conceder o grupo.
        grupo: grupo a conceder, ou ``None`` (sem grupo, sempre aceito).

    Raises:
        AlteracaoRecusada: se o grupo dá permissões que o autor não tem.

    English:
        Refuses granting a group with permissions the author lacks.

        Args:
            autor: user who wants to grant the group.
            grupo: group to grant, or ``None`` (no group, always
                accepted).

        Raises:
            AlteracaoRecusada: if the group grants permissions the author
                lacks.
    """
    if (
        grupo is not None
        and not grupos_que_pode_conceder(autor).filter(pk=grupo.pk).exists()
    ):
        raise AlteracaoRecusada(
            f"o grupo '{grupo.name}' dá permissões que você não tem"
        )


def pode_alterar(autor: User, alvo: User) -> bool:
    """Indica se ``autor`` pode alterar o acesso de ``alvo``.

    Usa as mesmas travas de ``_verificar_se_pode_alterar``, mas devolve um
    booleano em vez de levantar exceção. Serve para o template decidir se
    mostra os botões, sem repetir as regras.

    Args:
        autor: usuário que quer fazer a alteração.
        alvo: usuário que seria alterado.

    Returns:
        ``True`` se a alteração é permitida; ``False`` caso contrário.

    English:
        Tells whether ``autor`` may change ``alvo``'s access.

        It uses the same safeguards as ``_verificar_se_pode_alterar``, but
        returns a boolean instead of raising. It lets the template decide
        whether to show the buttons, without repeating the rules.

        Args:
            autor: user who wants to make the change.
            alvo: user who would be changed.

        Returns:
            ``True`` if the change is allowed; ``False`` otherwise.
    """
    try:
        _verificar_se_pode_alterar(autor, alvo)
    except AlteracaoRecusada:
        return False
    return True


@transaction.atomic
def trocar_grupo(autor: User, alvo: User, grupo: Group | None) -> None:
    """Substitui o grupo do usuário e registra a troca na auditoria.

    No Maestro cada usuário tem no máximo um grupo, por isso usamos
    ``groups.set([grupo])``, que remove os anteriores e deixa só o novo.
    O detalhe registrado fica no formato
    ``usuario: grupo antigo → grupo novo``.

    Args:
        autor: usuário que faz a alteração.
        alvo: usuário que terá o grupo trocado.
        grupo: novo grupo, ou ``None`` para deixar o usuário sem grupo.

    Raises:
        AlteracaoRecusada: se as travas de acesso recusarem.

    English:
        Replaces the user's group and records the change in the audit log.

        In Maestro each user has at most one group, so we use
        ``groups.set([grupo])``, which removes the previous ones and keeps
        only the new one. The recorded detail looks like
        ``user: old group → new group``.

        Args:
            autor: user making the change.
            alvo: user whose group will change.
            grupo: new group, or ``None`` to leave the user without a
                group.

        Raises:
            AlteracaoRecusada: if the access safeguards refuse.
    """
    _verificar_se_pode_alterar(autor, alvo)
    _verificar_grupo(autor, grupo)

    anteriores = (
        ", ".join(alvo.groups.values_list("name", flat=True)) or "sem grupo"
    )
    novo = grupo.name if grupo else "sem grupo"

    if grupo:
        alvo.groups.set([grupo])
    else:
        alvo.groups.clear()

    RegistroAcesso.objects.create(
        autor=autor,
        alvo=alvo,
        acao=RegistroAcesso.Acao.GRUPO,
        detalhe=f"{alvo.username}: {anteriores} → {novo}",
    )


@transaction.atomic
def alternar_ativo(autor: User, alvo: User) -> None:
    """Desativa um usuário ativo ou reativa um desativado.

    Desativar (``is_active = False``) é melhor do que excluir: o usuário
    não consegue mais entrar, mas o histórico dele (robôs, execuções,
    registros) continua intacto.

    Args:
        autor: usuário que faz a alteração.
        alvo: usuário a ser desativado ou reativado.

    Raises:
        AlteracaoRecusada: se as travas de acesso recusarem.

    English:
        Deactivates an active user or reactivates a deactivated one.

        Deactivating (``is_active = False``) is better than deleting: the
        user can no longer log in, but their history (robots, executions,
        records) stays intact.

        Args:
            autor: user making the change.
            alvo: user to deactivate or reactivate.

        Raises:
            AlteracaoRecusada: if the access safeguards refuse.
    """
    _verificar_se_pode_alterar(autor, alvo)

    alvo.is_active = not alvo.is_active
    alvo.save(update_fields=["is_active"])

    RegistroAcesso.objects.create(
        autor=autor,
        alvo=alvo,
        acao=(
            RegistroAcesso.Acao.REATIVACAO
            if alvo.is_active
            else RegistroAcesso.Acao.DESATIVACAO
        ),
        detalhe=alvo.username,
    )


@transaction.atomic
def criar_usuario(autor: User, form: NovoUsuarioForm) -> User:
    """Cria o usuário do formulário, com o grupo escolhido, e registra.

    O formulário já validou os dados e cuida da senha (``set_password``
    gravando só o hash). Aqui ficam o grupo e a auditoria, dentro da mesma
    transação: se o registro falhar, o usuário também não é criado.

    Nada aqui toca ``is_superuser`` ou ``is_staff``: quem nasce pela tela
    é sempre um usuário comum.

    Args:
        autor: usuário que está criando a conta.
        form: ``NovoUsuarioForm`` já validado (``is_valid()`` verdadeiro).

    Raises:
        AlteracaoRecusada: se o grupo dá permissões que o autor não tem.

    Returns:
        O usuário criado.

    English:
        Creates the user from the form, with the chosen group, and logs it.

        The form already validated the data and handles the password
        (``set_password`` storing only the hash). The group and the audit
        record live here, in the same transaction: if the record fails, the
        user is not created either.

        Nothing here touches ``is_superuser`` or ``is_staff``: anyone
        created through the page is always a regular user.

        Args:
            autor: user creating the account.
            form: a validated ``NovoUsuarioForm`` (``is_valid()`` is true).

        Raises:
            AlteracaoRecusada: if the group grants permissions the author
                lacks.

        Returns:
            The created user.
    """
    grupo = form.cleaned_data["grupo"]
    _verificar_grupo(autor, grupo)
    usuario = form.save()
    if grupo:
        usuario.groups.set([grupo])

    RegistroAcesso.objects.create(
        autor=autor,
        alvo=usuario,
        acao=RegistroAcesso.Acao.CRIACAO,
        detalhe=f"{usuario.username} ({grupo.name if grupo else 'sem grupo'})",
    )
    return usuario


def limite_da_retencao(agora: datetime | None = None) -> datetime:
    """Calcula a data antes da qual o histórico pode ser apagado.

    Args:
        agora: momento de referência; ``None`` usa a hora atual.

    Returns:
        ``agora`` menos os dias de retenção configurados.

    English:
        Computes the date before which history may be deleted.

        Args:
            agora: reference moment; ``None`` uses the current time.

        Returns:
            ``agora`` minus the configured retention days.
    """
    agora = agora or timezone.now()
    dias = ConfiguracaoSistema.atual().retencao_dias
    return agora - timedelta(days=dias)


def limpar_historico(agora: datetime | None = None) -> int:
    """Apaga as execuções finalizadas há mais tempo que a retenção.

    Só entram execuções finalizadas (``sucesso``, ``falha`` ou
    ``cancelada``) com ``finalizado_em`` antes do limite. Execuções
    ``pendente`` ou ``rodando`` nunca são apagadas, por mais antigas que
    sejam: ainda podem estar em uso pelo worker. O log mora no próprio
    registro, então vai junto.

    Args:
        agora: momento de referência; ``None`` usa a hora atual.

    Returns:
        Quantidade de execuções apagadas.

    English:
        Deletes executions finished longer ago than the retention period.

        Only finished executions (``sucesso``, ``falha`` or
        ``cancelada``) with ``finalizado_em`` before the limit are
        included. ``pendente`` or ``rodando`` executions are never
        deleted, however old: the worker may still be using them. The log
        lives in the record itself, so it goes too.

        Args:
            agora: reference moment; ``None`` uses the current time.

        Returns:
            Number of deleted executions.
    """
    _, apagados_por_model = Execucao.objects.filter(
        status__in=STATUS_FINALIZADOS,
        finalizado_em__lt=limite_da_retencao(agora),
    ).delete()
    return apagados_por_model.get("executions.Execucao", 0)
