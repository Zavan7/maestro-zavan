"""Aplicação Celery do Maestro e agenda das tarefas periódicas.

O Celery executa trabalho fora da requisição web: a view só registra o
pedido e um worker roda o robô em segundo plano, sem travar a tela.

Pontos que valem entender:

- ``config_from_object`` com ``namespace="CELERY"`` faz o Celery ler
  do ``settings.py`` só as variáveis que começam com ``CELERY_``.
- ``autodiscover_tasks`` procura um ``tasks.py`` em cada app instalado.
- ``beat_schedule`` é a agenda do ``celery beat``: aqui ele chama
  ``verificar_agendamentos`` uma vez por minuto (``crontab(minute="*")``).

English:
    Maestro's Celery application and periodic task schedule.

    Celery runs work outside the web request: the view only records the
    request and a worker runs the robot in the background, without
    freezing the page.

    Worth understanding:

    - ``config_from_object`` with ``namespace="CELERY"`` makes Celery
      read only the ``settings.py`` variables that start with
      ``CELERY_``.
    - ``autodiscover_tasks`` looks for a ``tasks.py`` in each installed
      app.
    - ``beat_schedule`` is the ``celery beat`` schedule: here it calls
      ``verificar_agendamentos`` once a minute
      (``crontab(minute="*")``).
"""
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")

app = Celery("maestro")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.beat_schedule = {
    "verificar-agendamentos": {
        "task": "scheduler.tasks.verificar_agendamentos",
        "schedule": crontab(minute="*"),
    },
}
