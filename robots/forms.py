"""Formulários do app de robôs.

English:
    Forms for the robots app.
"""
from django import forms

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

        English:
            Binds the form to the model and lists the editable fields.
        """

        model = Robo
        fields = ["nome", "descricao", "caminho_script", "status"]
