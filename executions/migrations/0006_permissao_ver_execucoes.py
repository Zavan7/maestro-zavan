"""Dá aos três grupos a permissão de ver execuções e logs.

Ver o histórico e o log de uma execução passou a exigir
``executions.view_execucao`` (antes bastava estar logado, e um usuário
sem grupo lia todos os logs). Os grupos que já usavam a tela a recebem
aqui; um usuário sem grupo deixa de ver os logs.

English:
    Gives the three groups the permission to view executions and logs.

    Viewing an execution's history and log now requires
    ``executions.view_execucao`` (before, being logged in was enough, and
    a user with no group read every log). The groups that already used
    the page get it here; a user with no group no longer sees the logs.
"""

from django.db import migrations

from config.migrations import _comum

GRUPOS = ["Operador", "Administrador RPA", "Administrador do sistema"]


def dar_permissao(apps, schema_editor):
    """Acrescenta ``executions.view_execucao`` aos três grupos.

    English:
        Adds ``executions.view_execucao`` to the three groups.
    """
    _comum.garantir_permissoes(apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    permissao = Permission.objects.get(
        content_type__app_label="executions", codename="view_execucao"
    )
    for nome in GRUPOS:
        grupo, _ = Group.objects.get_or_create(name=nome)
        grupo.permissions.add(permissao)


class Migration(migrations.Migration):
    """Migração de dados da permissão de ver execuções.

    English:
        Data migration for the permission to view executions.
    """

    dependencies = [
        ("auth", "__latest__"),
        ("contenttypes", "__latest__"),
        ("config", "0007_grupo_gerencia_agentes"),
        ("executions", "0005_total_linhas"),
    ]

    operations = [
        migrations.RunPython(dar_permissao, migrations.RunPython.noop)
    ]
