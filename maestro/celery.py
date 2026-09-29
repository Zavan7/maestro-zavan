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