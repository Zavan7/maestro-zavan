from django.db import models
from django.conf import settings
from robots.models import Robo


class Execucao(models.Model):
    class Status(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        RODANDO = "rodando", "Rodando"
        SUCESSO = "sucesso", "Sucesso"
        FALHA = "falha", "Falha"

    robo = models.ForeignKey(
        Robo,
        on_delete=models.PROTECT,
        related_name="execucoes",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDENTE,
    )
    disparado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execucoes_disparadas",
    )
    iniciado_em = models.DateTimeField(null=True, blank=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    log = models.TextField(blank=True)

    def __str__(self):
        return f"{self.robo.nome} — {self.get_status_display()}"

    @property
    def duracao_formatada(self):
        if not (self.iniciado_em and self.finalizado_em):
            return ""

        segundos = int((self.finalizado_em - self.iniciado_em).total_seconds())
        minutos, segundos = divmod(segundos, 60)
        horas, minutos = divmod(minutos, 60)

        if horas:
            return f"{horas}h{minutos:02d}m"
        if minutos:
            return f"{minutos}m{segundos:02d}s"
        return f"{segundos}s"