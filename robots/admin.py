from django.contrib import admin
from robots.models import Robo


@admin.register(Robo)
class RoboAdmin(admin.ModelAdmin):
    list_display = ("nome", "status", "responsavel", "criado_em")
    list_filter = ("status",)