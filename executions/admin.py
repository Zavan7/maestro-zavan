"""Admin do app de execuções.

English:
    Admin for the executions app.
"""

from django.contrib import admin

from executions.models import Execucao


@admin.register(Execucao)
class ExecucaoAdmin(admin.ModelAdmin):
    """Configura como as execuções aparecem no admin do Django.

    English:
        Configures how executions appear in the Django admin.
    """

    list_display = (
        "robo",
        "status",
        "disparado_por",
        "iniciado_em",
        "finalizado_em",
    )
    list_filter = ("status",)
