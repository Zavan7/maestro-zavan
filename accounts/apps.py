"""Configuração do app de contas.

English:
    Configuration for the accounts app.
"""
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Registra o app ``accounts`` no Django.

    O Django usa esta classe, referenciada em ``INSTALLED_APPS``, para
    saber o nome do app e onde procurar models, templates e migrations.

    English:
        Registers the ``accounts`` app with Django.

        Django uses this class, referenced in ``INSTALLED_APPS``, to learn
        the app's name and where to look for models, templates and
        migrations.
    """

    name = "accounts"
