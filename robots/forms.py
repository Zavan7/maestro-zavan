"""Formulários do app de robôs.

English:
    Forms for the robots app.
"""

from typing import Any

from django import forms
from django.db.models import Q

from agents.models import Agente
from robots.models import Robo


class RoboForm(forms.ModelForm):
    """Formulário de cadastro e edição de robô.

    Por ser um ``ModelForm``, ele gera os campos e as validações a partir
    do model ``Robo``. O ``responsavel`` fica de fora de ``fields`` de
    propósito: quem define o responsável é a view (o usuário logado), e
    não o que vem do navegador, que poderia ser adulterado.

    English:
        Form for creating and editing a robot.

        Being a ``ModelForm``, it builds its fields and validation from the
        ``Robo`` model. ``responsavel`` is left out of ``fields`` on
        purpose: the view sets the owner (the logged-in user), not data
        coming from the browser, which could be tampered with.
    """

    class Meta:
        """Liga o formulário ao model e lista os campos editáveis.

        Os rótulos são curtos e em minúsculas, como no resto do Maestro;
        as explicações maiores vêm do ``help_text`` do model.

        English:
            Binds the form to the model and lists the editable fields.

            The labels are short and lowercase, like the rest of Maestro;
            the longer explanations come from the model's ``help_text``.
        """

        model = Robo
        fields = [
            "nome",
            "descricao",
            "caminho_script",
            "status",
            "timeout_segundos",
            "max_tentativas",
            "duracao_esperada_segundos",
            "agente",
        ]
        labels = {
            "nome": "nome",
            "descricao": "descrição",
            "caminho_script": "caminho do script",
            "status": "status",
            "timeout_segundos": "tempo máximo (segundos)",
            "max_tentativas": "novas tentativas após falha",
            "duracao_esperada_segundos": "duração esperada (segundos)",
            "agente": "agente",
        }
        widgets = {"descricao": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Monta o formulário oferecendo só agentes ativos.

        Um robô que já aponta para um agente desativado continua vendo
        esse agente na lista, para a edição não trocar de máquina sem
        querer.

        English:
            Builds the form offering only active agents.

            A robot already pointing to a deactivated agent still sees
            that agent in the list, so editing does not switch machines by
            accident.
        """
        super().__init__(*args, **kwargs)
        campo = self.fields["agente"]
        assert isinstance(campo, forms.ModelChoiceField)
        atual = self.instance.agente_id if self.instance.pk else None
        campo.queryset = Agente.objects.filter(
            Q(ativo=True) | Q(pk=atual)
        ).order_by("nome")
        campo.empty_label = "nenhum (worker do Maestro)"
