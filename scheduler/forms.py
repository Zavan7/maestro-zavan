"""Formulários do app de agendamentos.

English:
    Forms for the schedules app.
"""
from django import forms

from robots.models import Robo
from scheduler.models import DIAS_DA_SEMANA, ROTULOS_CURTOS, Agendamento


class AgendamentoForm(forms.ModelForm):
    """Formulário de criação e edição de agendamento.

    Como em ``RoboForm``, o ``criado_por`` fica fora de ``fields``: quem o
    preenche é a view, com o usuário logado.

    English:
        Form for creating and editing a schedule.

        As in ``RoboForm``, ``criado_por`` is left out of ``fields``: the
        view fills it with the logged-in user.
    """

    class Meta:
        """Campos, rótulos curtos dos dias e o widget de horário.

        O ``*DIAS_DA_SEMANA`` "desempacota" a tupla dentro da lista, e o
        ``**ROTULOS_CURTOS`` faz o mesmo com o dicionário. O widget
        ``TimeInput`` com ``type="time"`` faz o navegador mostrar o seletor de
        horário nativo.

        English:
            Fields, short day labels and the time widget.

            ``*DIAS_DA_SEMANA`` "unpacks" the tuple into the list, and
            ``**ROTULOS_CURTOS`` does the same with the dict. The ``TimeInput``
            widget with ``type="time"`` makes the browser show its native time
            picker.
        """

        model = Agendamento
        fields = ["robo", "horario", *DIAS_DA_SEMANA, "ativo"]
        labels = {"robo": "robô", "horario": "horário", **ROTULOS_CURTOS}
        widgets = {
            "horario": forms.TimeInput(
                attrs={"type": "time"}, format="%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        """Monta o formulário e ordena os robôs do select por nome.

        Primeiro chama o ``__init__`` original com ``super()``, que cria os
        campos; só depois troca o ``queryset`` do campo ``robo``.

        English:
            Builds the form and sorts the robot select by name.

            It first calls the original ``__init__`` with ``super()``, which
            creates the fields; only then does it replace the ``robo`` field's
            ``queryset``.
        """
        super().__init__(*args, **kwargs)
        self.fields["robo"].queryset = Robo.objects.order_by("nome")

    def campos_dos_dias(self):
        """Retorna os campos dos sete dias, na ordem da semana.

        Permite que o template desenhe os dias num loop
        (``{% for campo in form.campos_dos_dias %}``) em vez de repetir sete
        blocos iguais.

        Returns:
            Lista de ``BoundField``, de segunda a domingo.

        English:
            Returns the seven day fields, in weekday order.

            It lets the template draw the days in a loop
            (``{% for campo in form.campos_dos_dias %}``) instead of repeating
            seven identical blocks.

            Returns:
                List of ``BoundField``, Monday to Sunday.
        """
        return [self[dia] for dia in DIAS_DA_SEMANA]
