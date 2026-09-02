from django.contrib import admin
from executions.models import Execucao


@admin.register(Execucao)
class ExecucaoAdmin(admin.ModelAdmin):
    list_display = ("robo", "status", "disparado_por", "iniciado_em", "finalizado_em")
    list_filter = ("status",)