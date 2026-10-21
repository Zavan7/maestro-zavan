"""Configuração do app de agendamentos.

English:
    Configuration for the schedules app.
"""

from django.apps import AppConfig


class SchedulerConfig(AppConfig):
    """Registra o app ``scheduler`` no Django.

    English:
        Registers the ``scheduler`` app with Django.
    """

    name = "scheduler"
