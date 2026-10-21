"""Formulários da aba de configurações.

English:
    Forms for the settings tab.
"""

from typing import Any

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User

from config.models import ConfiguracaoSistema


class RetencaoForm(forms.ModelForm):
    """Edita por quantos dias o histórico de execuções é guardado.

    Os limites (7 a 3650 dias) vêm dos validadores do próprio model, então
    o formulário não repete as regras.

    English:
        Edits how many days the execution history is kept.

        The limits (7 to 3650 days) come from the model's own validators,
        so the form does not repeat the rules.
    """

    class Meta:
        """Só o campo de retenção, com rótulo curto.

        English:
            Only the retention field, with a short label.
        """

        model = ConfiguracaoSistema
        fields = ["retencao_dias"]
        labels = {"retencao_dias": "dias de retenção"}


class LimitesForm(forms.ModelForm):
    """Edita os limites padrão de execução dos robôs.

    O tempo máximo vale para robôs que não definem o próprio; o limite do
    log vale para todos. Os mínimos e máximos vêm dos validadores do
    model.

    English:
        Edits the robots' default execution limits.

        The maximum time applies to robots that set none of their own; the
        log limit applies to all of them. Minimums and maximums come from
        the model's validators.
    """

    class Meta:
        """Os dois limites, com rótulos curtos.

        English:
            Both limits, with short labels.
        """

        model = ConfiguracaoSistema
        fields = ["timeout_padrao_segundos", "limite_log"]
        labels = {
            "timeout_padrao_segundos": "tempo máximo por execução (segundos)",
            "limite_log": "tamanho máximo do log (caracteres)",
        }


class NovoUsuarioForm(UserCreationForm):
    """Cadastro de usuário pela aba de configurações, já com o grupo.

    Herda de ``UserCreationForm``, que confere se as duas senhas batem,
    aplica os validadores de senha do ``settings`` e grava só o hash. Os
    campos de superusuário e de equipe ficam de fora de propósito.

    O ``queryset`` dos grupos é preguiçoso: o Django copia e reavalia a
    consulta a cada formulário, então um grupo novo aparece sem reiniciar
    o servidor.

    English:
        User sign-up through the settings tab, with the group included.

        It inherits from ``UserCreationForm``, which checks that both
        passwords match, applies the password validators from ``settings``
        and stores only the hash. The superuser and staff fields are left
        out on purpose.

        The groups ``queryset`` is lazy: Django copies and re-runs the
        query for each form, so a new group shows up without restarting
        the server.
    """

    grupo = forms.ModelChoiceField(
        queryset=Group.objects.order_by("name"),
        required=False,
        empty_label="sem grupo",
        label="grupo",
    )

    class Meta(UserCreationForm.Meta):
        """Campos do usuário, além das senhas e do grupo.

        English:
            User fields, besides the passwords and the group.
        """

        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "usuário",
            "first_name": "nome",
            "last_name": "sobrenome",
            "email": "e-mail",
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Monta o formulário com os rótulos de senha em minúsculas.

        Os campos de senha são declarados pelo ``UserCreationForm``, e não
        pela ``Meta``; por isso o ``labels`` acima não os alcança e os
        rótulos são trocados aqui, depois do ``super()``.

        English:
            Builds the form with lowercase password labels.

            The password fields are declared by ``UserCreationForm``, not by
            ``Meta``; that is why ``labels`` above does not reach them and
            the labels are changed here, after ``super()``.
        """
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "senha"
        self.fields["password2"].label = "confirmação da senha"
