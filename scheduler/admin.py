from django.contrib import admin

from scheduler.models import Agendamento


@admin.register(Agendamento)
class AgendamentoAdmin(admin.ModelAdmin):
    list_display = ("robo", "horario", "dias_formatados", "ativo", "ultimo_disparo")
    list_filter = ("ativo",)
    readonly_fields = ("ultimo_disparo", "criado_em")