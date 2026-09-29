from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from robots.models import Robo

DIAS_DA_SEMANA = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")

ROTULOS_CURTOS = {
    "segunda": "seg",
    "terca": "ter",
    "quarta": "qua",
    "quinta": "qui",
    "sexta": "sex",
    "sabado": "sáb",
    "domingo": "dom",
}


def formatar_proxima(momento, agora):
    horario = momento.strftime("%H:%M")
    dias = (momento.date() - agora.date()).days
    if dias == 0:
        return f"hoje {horario}"
    if dias == 1:
        return f"amanhã {horario}"
    return f"{ROTULOS_CURTOS[DIAS_DA_SEMANA[momento.weekday()]]} {horario}"


class Agendamento(models.Model):
    robo = models.ForeignKey(
        Robo,
        on_delete=models.CASCADE,
        related_name="agendamentos",
    )
    horario = models.TimeField()

    segunda = models.BooleanField(default=True)
    terca = models.BooleanField(default=True)
    quarta = models.BooleanField(default=True)
    quinta = models.BooleanField(default=True)
    sexta = models.BooleanField(default=True)
    sabado = models.BooleanField(default=False)
    domingo = models.BooleanField(default=False)

    ativo = models.BooleanField(default=True)
    ultimo_disparo = models.DateTimeField(null=True, blank=True, editable=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["horario"]
        constraints = [
            models.UniqueConstraint(
                fields=["robo", "horario"],
                name="agendamento_unico_por_horario",
            ),
        ]

    def __str__(self):
        return f"{self.robo.nome} às {self.horario:%H:%M}"

    def clean(self):
        if not any(getattr(self, dia) for dia in DIAS_DA_SEMANA):
            raise ValidationError("Escolha pelo menos um dia da semana.")

    def save(self, *args, **kwargs):
        self.horario = self.horario.replace(second=0, microsecond=0)
        super().save(*args, **kwargs)

    def dias_formatados(self):
        ativos = [ROTULOS_CURTOS[dia] for dia in DIAS_DA_SEMANA if getattr(self, dia)]
        if len(ativos) == 7:
            return "todos os dias"
        if ativos == ["seg", "ter", "qua", "qui", "sex"]:
            return "dias úteis"
        return ", ".join(ativos)

    dias_formatados.short_description = "dias"

    def proxima_ocorrencia(self, agora=None):
        agora = agora or timezone.localtime()
        for deslocamento in range(8):
            dia = agora.date() + timedelta(days=deslocamento)
            if not getattr(self, DIAS_DA_SEMANA[dia.weekday()]):
                continue
            momento = timezone.make_aware(datetime.combine(dia, self.horario))
            if momento > agora:
                return momento
        return None