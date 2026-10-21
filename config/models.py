"""Models do app de configurações.

English:
    Models for the settings app.
"""

from typing import Any, Self

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ConfiguracaoSistema(models.Model):
    """Configuração global do sistema, guardada num único registro.

    Este é o padrão "singleton": só existe uma linha na tabela, sempre com
    ``pk=1``. Para ler, use ``ConfiguracaoSistema.atual()``.

    O model também serve de "dono" das permissões da aba de configurações
    (veja ``Meta.permissions``).

    English:
        Global system settings, stored in a single record.

        This is the "singleton" pattern: the table has only one row, always
        with ``pk=1``. To read it, use ``ConfiguracaoSistema.atual()``.

        The model also acts as the "owner" of the settings tab permissions
        (see ``Meta.permissions``).
    """

    retencao_dias = models.PositiveIntegerField(
        default=90,
        validators=[MinValueValidator(7), MaxValueValidator(3650)],
        help_text="Por quantos dias guardar execuções e logs.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        """Troca as permissões padrão pelas permissões próprias da aba.

        ``default_permissions = ()`` desliga ``add``, ``change``, ``delete`` e
        ``view``, que não fazem sentido num registro único. No lugar, cada
        seção da aba ganha a sua permissão.

        English:
            Swaps the default permissions for the tab's own permissions.

            ``default_permissions = ()`` turns off ``add``, ``change``,
            ``delete`` and ``view``, which make no sense for a single record.
            Instead, each section of the tab gets its own permission.
        """

        verbose_name = "configuração do sistema"
        default_permissions = ()
        permissions = [
            ("gerenciar_usuarios", "Pode gerenciar usuários e acesso"),
            ("ver_status_sistema", "Pode ver o status do sistema"),
            ("gerenciar_retencao", "Pode alterar a retenção do histórico"),
            (
                "gerenciar_limites",
                "Pode alterar os limites padrão de execução",
            ),
        ]

    def __str__(self) -> str:
        """Retorna um nome fixo, já que só existe um registro.

        English:
            Returns a fixed name, since there is only one record.
        """
        return "Configuração do sistema"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Salva sempre com ``pk=1``, mantendo um registro só.

        Mesmo criando uma instância nova, o ``pk`` forçado faz o Django
        atualizar a linha existente em vez de criar outra.

        English:
            Always saves with ``pk=1``, keeping a single record.

            Even when creating a new instance, the forced ``pk`` makes Django
            update the existing row instead of creating another one.
        """
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def atual(cls) -> Self:
        """Retorna a configuração, criando-a com os valores padrão se faltar.

        ``get_or_create`` devolve uma tupla ``(objeto, criado)``; o ``_``
        descarta o segundo valor, que não é usado aqui.

        Returns:
            A instância única de ``ConfiguracaoSistema``.

        English:
            Returns the settings, creating them with default values if missing.

            ``get_or_create`` returns a tuple ``(object, created)``; the ``_``
            discards the second value, which is not used here.

            Returns:
                The single ``ConfiguracaoSistema`` instance.
        """
        configuracao, _ = cls.objects.get_or_create(pk=1)
        return configuracao


class RegistroAcesso(models.Model):
    """Registro de auditoria das alterações de acesso.

    Toda criação, troca de grupo, desativação ou reativação feita pela aba
    de usuários gera uma linha aqui, dizendo quem fez (``autor``), com quem
    (``alvo``) e o que mudou (``detalhe``). Os dois usam ``SET_NULL`` para
    que o registro sobreviva mesmo se um dos usuários for excluído.

    English:
        Audit log of access changes.

        Every creation, group change, deactivation or reactivation made
        through the users tab creates a row here, saying who did it
        (``autor``), to whom (``alvo``) and what changed (``detalhe``).
        Both use ``SET_NULL`` so the record survives even if one of the
        users is deleted.
    """

    class Acao(models.TextChoices):
        """Tipo de alteração registrada.

        English:
            Kind of change recorded.
        """

        CRIACAO = "criacao", "Criação"
        GRUPO = "grupo", "Troca de grupo"
        DESATIVACAO = "desativacao", "Desativação"
        REATIVACAO = "reativacao", "Reativação"

    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="alteracoes_feitas",
    )
    alvo = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="alteracoes_recebidas",
    )
    acao = models.CharField(max_length=20, choices=Acao.choices)
    detalhe = models.CharField(max_length=255, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Mostra os registros mais recentes primeiro, sem permissões padrão.

        English:
            Shows the newest records first, without default permissions.
        """

        ordering = ["-criado_em"]
        default_permissions = ()

    def __str__(self) -> str:
        """Retorna a ação e o detalhe, por exemplo ``Desativação: analista``.

        English:
            Returns the action and the detail, e.g. ``Desativação: analista``.
        """
        return f"{self.get_acao_display()}: {self.detalhe}"
