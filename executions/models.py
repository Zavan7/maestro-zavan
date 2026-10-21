"""Models do app de execuções.

English:
    Models for the executions app.
"""
from django.conf import settings
from django.db import models

from robots.models import Robo


class Execucao(models.Model):
    """Uma execução de robô: quando rodou, como terminou e o que imprimiu.

    Escolhas de ``on_delete`` e o motivo de cada uma:

    - ``robo`` usa ``PROTECT``: o histórico é valioso, então um robô com
      execuções não pode ser excluído.
    - ``agendamento`` e ``disparado_por`` usam ``SET_NULL``: se o
      agendamento ou o usuário sumirem, a execução continua no histórico,
      só sem essa referência.

    English:
        A robot execution: when it ran, how it ended and what it printed.

        ``on_delete`` choices and the reason for each one:

        - ``robo`` uses ``PROTECT``: history is valuable, so a robot with
          executions cannot be deleted.
        - ``agendamento`` and ``disparado_por`` use ``SET_NULL``: if the
          schedule or the user disappears, the execution stays in the
          history, just without that reference.
    """

    class Status(models.TextChoices):
        """Ciclo de vida da execução.

        ``PENDENTE`` (criada, esperando o worker) → ``RODANDO`` (script em
        andamento) → ``SUCESSO`` ou ``FALHA``. ``CANCELADA`` é quando um
        usuário mandou parar, ainda na fila ou já rodando.

        English:
            Execution life cycle.

            ``PENDENTE`` (created, waiting for the worker) → ``RODANDO``
            (script running) → ``SUCESSO`` or ``FALHA``. ``CANCELADA`` is
            when a user asked to stop, while queued or already running.
        """

        PENDENTE = "pendente", "Pendente"
        RODANDO = "rodando", "Rodando"
        SUCESSO = "sucesso", "Sucesso"
        FALHA = "falha", "Falha"
        CANCELADA = "cancelada", "Cancelada"

    class Origem(models.TextChoices):
        """De onde veio o disparo.

        ``MANUAL`` quando um usuário clicou em "iniciar"; ``AGENDAMENTO``
        quando o agendador disparou sozinho.

        English:
            Where the trigger came from.

            ``MANUAL`` when a user clicked "start"; ``AGENDAMENTO`` when the
            scheduler triggered it on its own.
        """

        MANUAL = "manual", "Manual"
        AGENDAMENTO = "agendamento", "Agendamento"

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
    origem = models.CharField(
        max_length=20,
        choices=Origem.choices,
        default=Origem.MANUAL,
    )
    agendamento = models.ForeignKey(
        "scheduler.Agendamento",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="execucoes",
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
    tentativa = models.PositiveSmallIntegerField(default=1)
    parada_solicitada = models.BooleanField(default=False)

    def __str__(self):
        """Retorna o nome do robô e o status, por exemplo ``robo-x — Falha``.

        English:
            Returns the robot name and status, e.g. ``robo-x — Falha``.
        """
        return f"{self.robo.nome} — {self.get_status_display()}"

    @property
    def duracao_formatada(self):
        """Duração da execução em formato curto e legível.

        Por ser uma ``@property``, é usada no template sem parênteses
        (``{{ execucao.duracao_formatada }}``). ``divmod`` divide e devolve o
        quociente e o resto de uma vez, o que facilita converter segundos em
        horas, minutos e segundos.

        Returns:
            ``1h05m``, ``3m07s`` ou ``42s``; texto vazio se a execução ainda
            não começou ou não terminou.

        English:
            Execution duration in a short, readable format.

            Being a ``@property``, it is used in templates without parentheses
            (``{{ execucao.duracao_formatada }}``). ``divmod`` divides and
            returns the quotient and the remainder at once, which makes it easy
            to turn seconds into hours, minutes and seconds.

            Returns:
                ``1h05m``, ``3m07s`` or ``42s``; an empty string if the
                execution has not started or finished yet.
        """
        if not (self.iniciado_em and self.finalizado_em):
            return ""

        segundos = int(
            (self.finalizado_em - self.iniciado_em).total_seconds()
        )
        minutos, segundos = divmod(segundos, 60)
        horas, minutos = divmod(minutos, 60)

        if horas:
            return f"{horas}h{minutos:02d}m"
        if minutos:
            return f"{minutos}m{segundos:02d}s"
        return f"{segundos}s"
