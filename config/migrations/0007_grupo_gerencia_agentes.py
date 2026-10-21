"""Dá ao grupo Administrador do sistema a permissão de gerenciar agentes.

Segue o padrão de ``0002_grupos_de_acesso``: garante que as permissões
existam (num banco novo, a migração roda antes de o Django criá-las) e
só acrescenta, sem remover nada que já esteja no grupo.

English:
    Gives the system administrator group the permission to manage agents.

    It follows the pattern of ``0002_grupos_de_acesso``: it makes sure
    the permissions exist (on a new database, the migration runs before
    Django creates them) and only adds, never removing anything already
    in the group.
"""

from django.db import migrations

from config.migrations import _comum


def dar_permissao(apps, schema_editor):
    """Acrescenta ``config.gerenciar_agentes`` ao Administrador do sistema.

    English:
        Adds ``config.gerenciar_agentes`` to the system administrator.
    """
    _comum.garantir_permissoes(apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    grupo, _ = Group.objects.get_or_create(name="Administrador do sistema")
    grupo.permissions.add(
        Permission.objects.get(
            content_type__app_label="config", codename="gerenciar_agentes"
        )
    )


class Migration(migrations.Migration):
    """Migração de dados da permissão de agentes.

    English:
        Data migration for the agents permission.
    """

    dependencies = [
        ("auth", "__latest__"),
        ("contenttypes", "__latest__"),
        ("config", "0006_permissao_e_registro_de_agentes"),
    ]

    operations = [migrations.RunPython(dar_permissao, migrations.RunPython.noop)]
