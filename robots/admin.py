"""Admin do app de robôs.

English:
    Admin for the robots app.
"""

from django.contrib import admin

from robots.models import Robo


@admin.register(Robo)
class RoboAdmin(admin.ModelAdmin):
    """Configura como os robôs aparecem no admin do Django.

    ``list_display`` define as colunas da listagem e ``list_filter`` cria o
    filtro lateral por status.

    English:
        Configures how robots appear in the Django admin.

        ``list_display`` sets the list columns and ``list_filter`` adds the
        status filter on the side.
    """

    list_display = ("nome", "status", "responsavel", "criado_em")
    list_filter = ("status",)
