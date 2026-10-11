"""Serviços de gestão de acesso, com travas de segurança e auditoria.

As regras ficam aqui, longe das views, para valerem em qualquer lugar
que altere acesso. As funções que alteram dados usam
``@transaction.atomic``: ou a alteração e o registro de auditoria são
gravados juntos, ou nada é gravado.

English:
    Access management services, with safety checks and auditing.

    The rules live here, away from the views, so they apply anywhere
    access is changed. Functions that change data use
    ``@transaction.atomic``: either the change and its audit record are
    saved together, or nothing is saved.
"""
from django.db import transaction

from config.models import RegistroAcesso


class AlteracaoRecusada(Exception):
    """Indica que a alteração de acesso não é permitida.

    A mensagem diz o motivo, pronta para aparecer ao usuário.

    English:
        Signals that the access change is not allowed.

        The message states the reason, ready to be shown to the user.
    """


def _verificar_se_pode_alterar(autor, alvo):
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


def pode_alterar(autor, alvo):
    """Indica se ``autor`` pode alterar o acesso de ``alvo``.

    Usa as mesmas travas de ``_verificar_se_pode_alterar``, mas devolve um
    booleano em vez de levantar exceção. Serve para o template decidir se
    mostra os botões, sem repetir as regras.

    Returns:
        ``True`` se a alteração é permitida; ``False`` caso contrário.

    English:
        Tells whether ``autor`` may change ``alvo``'s access.

        It uses the same safeguards as ``_verificar_se_pode_alterar``, but
        returns a boolean instead of raising. It lets the template decide
        whether to show the buttons, without repeating the rules.

        Returns:
            ``True`` if the change is allowed; ``False`` otherwise.
    """
    try:
        _verificar_se_pode_alterar(autor, alvo)
    except AlteracaoRecusada:
        return False
    return True


@transaction.atomic
def trocar_grupo(autor, alvo, grupo):
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
def alternar_ativo(autor, alvo):
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
