"""Models do app de agendamentos e utilitários de data.

``DIAS_DA_SEMANA`` segue a ordem de ``date.weekday()`` (segunda = 0,
domingo = 6). Por isso ``DIAS_DA_SEMANA[data.weekday()]`` devolve o
nome do campo booleano daquele dia.

English:
    Models for the schedules app and date helpers.

    ``DIAS_DA_SEMANA`` follows ``date.weekday()`` order (Monday = 0,
    Sunday = 6). That is why ``DIAS_DA_SEMANA[date.weekday()]`` returns
    the name of that day's boolean field.
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from robots.models import Robo

DIAS_DA_SEMANA = (
    "segunda",
    "terca",
    "quarta",
    "quinta",
    "sexta",
    "sabado",
    "domingo",
)

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
    """Formata a próxima ocorrência de forma curta e relativa a ``agora``.

    Compara só as datas (sem as horas) para saber quantos dias faltam:
    0 vira "hoje", 1 vira "amanhã" e o resto mostra o dia da semana.

    Args:
        momento: data e hora da próxima ocorrência.
        agora: momento de referência.

    Returns:
        ``hoje HH:MM``, ``amanhã HH:MM`` ou ``<dia> HH:MM``
        (por exemplo, ``sex 08:00``).

    English:
        Formats the next run in a short form, relative to ``agora``.

        It compares only the dates (not the times) to find how many days
        are left: 0 becomes "hoje" (today), 1 becomes "amanhã" (tomorrow)
        and anything else shows the weekday.

        Args:
            momento: date and time of the next run.
            agora: reference time.

        Returns:
            ``hoje HH:MM``, ``amanhã HH:MM`` or ``<day> HH:MM``
            (e.g. ``sex 08:00``).
    """
    horario = momento.strftime("%H:%M")
    dias = (momento.date() - agora.date()).days
    if dias == 0:
        return f"hoje {horario}"
    if dias == 1:
        return f"amanhã {horario}"
    return f"{ROTULOS_CURTOS[DIAS_DA_SEMANA[momento.weekday()]]} {horario}"


class Agendamento(models.Model):
    """Disparo recorrente de um robô num horário, nos dias marcados.

    Cada dia da semana é um ``BooleanField`` (``segunda``...``domingo``).
    É simples de filtrar no banco: ``filter(segunda=True)``.

    O ``robo`` usa ``on_delete=CASCADE``: agendamento não faz sentido sem
    o robô, então some junto com ele. Já ``ultimo_disparo`` é a "trava"
    que impede disparar duas vezes no mesmo minuto (veja
    ``scheduler.tasks.verificar_agendamentos``).

    English:
        Recurring trigger of a robot at a set time, on the checked days.

        Each weekday is a ``BooleanField`` (``segunda``...``domingo``).
        It is easy to filter in the database: ``filter(segunda=True)``.

        ``robo`` uses ``on_delete=CASCADE``: a schedule makes no sense
        without its robot, so it goes away with it. ``ultimo_disparo`` is
        the "lock" that prevents triggering twice in the same minute (see
        ``scheduler.tasks.verificar_agendamentos``).
    """

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
    ultimo_disparo = models.DateTimeField(
        null=True, blank=True, editable=False
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agendamentos_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Ordena por horário e impede dois agendamentos iguais.

        A ``UniqueConstraint`` é garantida pelo próprio banco: o mesmo robô não
        pode ter dois agendamentos no mesmo horário.

        English:
            Orders by time and prevents duplicate schedules.

            The ``UniqueConstraint`` is enforced by the database itself: the
            same robot cannot have two schedules at the same time.
        """

        ordering = ["horario"]
        constraints = [
            models.UniqueConstraint(
                fields=["robo", "horario"],
                name="agendamento_unico_por_horario",
            ),
        ]

    def __str__(self):
        """Retorna o robô e o horário, por exemplo ``robo-x às 08:00``.

        English:
            Returns the robot and time, e.g. ``robo-x às 08:00``.
        """
        return f"{self.robo.nome} às {self.horario:%H:%M}"

    def clean(self):
        """Valida que pelo menos um dia da semana está marcado.

        O Django chama ``clean()`` durante a validação do formulário
        (``form.is_valid()``) e do ``full_clean()``. Um ``ValidationError``
        aqui aparece como erro geral do formulário.

        Raises:
            ValidationError: se nenhum dia estiver marcado.

        English:
            Validates that at least one weekday is checked.

            Django calls ``clean()`` during form validation
            (``form.is_valid()``) and ``full_clean()``. A ``ValidationError``
            here shows up as a general form error.

            Raises:
                ValidationError: if no day is checked.
        """
        if not any(getattr(self, dia) for dia in DIAS_DA_SEMANA):
            raise ValidationError("Escolha pelo menos um dia da semana.")

    def save(self, *args, **kwargs):
        """Zera segundos e microssegundos do horário antes de salvar.

        A tarefa compara o horário exato do minuto (por exemplo, ``08:00:00``).
        Se ficasse salvo ``08:00:30``, o agendamento nunca bateria.

        English:
            Clears seconds and microseconds from the time before saving.

            The task compares against the exact minute (e.g. ``08:00:00``). If
            ``08:00:30`` were saved, the schedule would never match.
        """
        self.horario = self.horario.replace(second=0, microsecond=0)
        super().save(*args, **kwargs)

    @admin.display(description="dias")
    def dias_formatados(self):
        """Resume os dias marcados em texto curto.

        Returns:
            ``todos os dias``, ``dias úteis`` ou a lista curta, como
            ``seg, sáb``.

        English:
            Summarizes the checked days in short text.

            Returns:
                ``todos os dias`` (every day), ``dias úteis`` (weekdays) or the
                short list, such as ``seg, sáb``.
        """
        ativos = [
            ROTULOS_CURTOS[dia] for dia in DIAS_DA_SEMANA if getattr(self, dia)
        ]
        if len(ativos) == 7:
            return "todos os dias"
        if ativos == ["seg", "ter", "qua", "qui", "sex"]:
            return "dias úteis"
        return ", ".join(ativos)

    def proxima_ocorrencia(self, agora=None):
        """Calcula quando será o próximo disparo a partir de ``agora``.

        Testa hoje e os próximos 7 dias (8 no total). Oito, e não sete, porque
        se só hoje estiver marcado e o horário de hoje já passou, a próxima
        ocorrência é no mesmo dia da semana seguinte.

        Args:
            agora: momento de referência; se omitido, usa a hora local atual.
                Receber ``agora`` como argumento facilita os testes, que podem
                fixar o relógio.

        Returns:
            O próximo ``datetime`` com fuso horário, ou ``None`` se nenhum dia
            estiver marcado.

        English:
            Computes when the next trigger will be, starting from ``agora``.

            It checks today and the next 7 days (8 in total). Eight, not seven,
            because if only today is checked and today's time has passed, the
            next run is on the same weekday next week.

            Args:
                agora: reference time; if omitted, uses the current local time.
                    Taking ``agora`` as an argument makes testing easier, since
                    tests can pin the clock.

            Returns:
                The next timezone-aware ``datetime``, or ``None`` if no day is
                checked.
        """
        agora = agora or timezone.localtime()
        for deslocamento in range(8):
            dia = agora.date() + timedelta(days=deslocamento)
            if not getattr(self, DIAS_DA_SEMANA[dia.weekday()]):
                continue
            momento = timezone.make_aware(datetime.combine(dia, self.horario))
            if momento > agora:
                return momento
        return None
