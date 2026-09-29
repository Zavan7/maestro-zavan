from django import forms

from robots.models import Robo
from scheduler.models import DIAS_DA_SEMANA, ROTULOS_CURTOS, Agendamento


class AgendamentoForm(forms.ModelForm):
    class Meta:
        model = Agendamento
        fields = ["robo", "horario", *DIAS_DA_SEMANA, "ativo"]
        labels = {"robo": "robô", "horario": "horário", **ROTULOS_CURTOS}
        widgets = {
            "horario": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["robo"].queryset = Robo.objects.order_by("nome")

    def campos_dos_dias(self):
        return [self[dia] for dia in DIAS_DA_SEMANA]