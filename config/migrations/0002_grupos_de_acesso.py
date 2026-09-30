from django.contrib.auth.management import create_permissions
from django.db import migrations

GRUPOS = {
    "Operador": [
        ("robots", "executar_robo"),
    ],
    "Administrador RPA": [
        ("robots", "executar_robo"),
        ("robots", "add_robo"),
        ("robots", "change_robo"),
        ("robots", "delete_robo"),
        ("robots", "view_robo"),
        ("scheduler", "add_agendamento"),
        ("scheduler", "change_agendamento"),
        ("scheduler", "delete_agendamento"),
        ("scheduler", "view_agendamento"),
    ],
    "Administrador do sistema": [
        ("robots", "executar_robo"),
        ("config", "gerenciar_usuarios"),
        ("config", "ver_status_sistema"),
        ("config", "gerenciar_retencao"),
        ("config", "gerenciar_limites"),
    ],
}


def garantir_permissoes(apps):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None


def criar_grupos(apps, schema_editor):
    garantir_permissoes(apps)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    for nome, permissoes in GRUPOS.items():
        grupo, _ = Group.objects.get_or_create(name=nome)
        for app_label, codename in permissoes:
            permissao = Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )
            grupo.permissions.add(permissao)


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "__latest__"),
        ("contenttypes", "__latest__"),
        ("config", "0001_initial"),
        ("robots", "0002_alter_robo_options"),
        ("scheduler", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_grupos, migrations.RunPython.noop),
    ]
