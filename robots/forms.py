from django import forms
from robots.models import Robo


class RoboForm(forms.ModelForm):
    class Meta:
        model = Robo
        fields = ["nome", "descricao", "caminho_script", "status"]