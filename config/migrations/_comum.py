"""Funções compartilhadas pelas migrações de dados do app ``config``.

O nome começa com ``_`` para o Django não tratar o arquivo como uma
migração.

English:
    Functions shared by the ``config`` app data migrations.

    The name starts with ``_`` so Django does not treat the file as a
    migration.
"""

from django.contrib.auth.management import create_permissions


def garantir_permissoes(apps):
    """Cria as permissões de todos os apps, se ainda não existirem.

    Num banco novo, as migrações rodam antes do sinal que cria as
    permissões; sem isto, ``Permission.objects.get`` daria
    ``DoesNotExist``.

    English:
        Creates every app's permissions, if they do not exist yet.

        On a new database, migrations run before the signal that creates
        permissions; without this, ``Permission.objects.get`` would raise
        ``DoesNotExist``.
    """
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None
