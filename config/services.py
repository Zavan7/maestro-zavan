from django.db import transaction

from config.models import RegistroAcesso


class AlteracaoRecusada(Exception):
    pass


def _verificar_se_pode_alterar(autor, alvo):
    if alvo.pk == autor.pk:
        raise AlteracaoRecusada("não é possível alterar o próprio acesso")
    if alvo.is_superuser and not autor.is_superuser:
        raise AlteracaoRecusada("só um superusuário pode alterar outro superusuário")


def pode_alterar(autor, alvo):
    try:
        _verificar_se_pode_alterar(autor, alvo)
    except AlteracaoRecusada:
        return False
    return True


@transaction.atomic
def trocar_grupo(autor, alvo, grupo):
    _verificar_se_pode_alterar(autor, alvo)

    anteriores = ", ".join(alvo.groups.values_list("name", flat=True)) or "sem grupo"
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
    _verificar_se_pode_alterar(autor, alvo)

    alvo.is_active = not alvo.is_active
    alvo.save(update_fields=["is_active"])

    RegistroAcesso.objects.create(
        autor=autor,
        alvo=alvo,
        acao=RegistroAcesso.Acao.REATIVACAO if alvo.is_active else RegistroAcesso.Acao.DESATIVACAO,
        detalhe=alvo.username,
    )
