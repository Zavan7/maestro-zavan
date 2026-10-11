"""Admin do app de agendamentos.

English:
    Admin for the schedules app.
"""
from django.contrib import admin

from scheduler.models import Agendamento


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    """Configura como os agendamentos aparecem no admin do Django.

    ``readonly_fields`` mostra os campos que o sistema preenche sozinho,
    mas impede que sejam editados à mão.

    English:
        Configures how schedules appear in the Django admin.

        ``readonly_fields`` shows the fields the system fills on its own,
        but prevents editing them by hand.
    """

    list_display = (
        "robo", "horario", "dias_formatados", "ativo", "ultimo_disparo"
    )
    list_filter = ("ativo",)
    readonly_fields = ("ultimo_disparo", "criado_em")
