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
        ]
        labels = {
            "nome": "nome",
            "descricao": "descrição",
            "caminho_script": "caminho do script",
            "status": "status",
            "timeout_segundos": "tempo máximo (segundos)",
            "max_tentativas": "novas tentativas após falha",
            "duracao_esperada_segundos": "duração esperada (segundos)",
        }
        widgets = {"descricao": forms.Textarea(attrs={"rows": 3})}
