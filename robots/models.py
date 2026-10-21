"""Models do app de robôs.

English:
    Models for the robots app.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Robo(models.Model):
    """Robô RPA cadastrado no Maestro.

    Cada robô aponta para um script Python dentro de
    ``settings.ROBOS_SCRIPTS_DIR``. O Maestro nunca executa um caminho
    qualquer: o caminho é sempre resolvido dentro dessa pasta (veja
    ``robots.tasks._resolver_script``).

    O ``responsavel`` usa ``on_delete=PROTECT``: um usuário responsável
    por robôs não pode ser excluído sem antes passar os robôs para outra
    pessoa, para não perder quem responde por eles.

    Com ``agente`` preenchido, o robô roda naquela máquina, e não no
    worker; o caminho do script passa a ser resolvido pelo agente, dentro
    da pasta aprovada dele. O ``PROTECT`` impede excluir um agente que
    ainda tem robôs: ninguém descobre na hora de rodar que o robô perdeu
    a máquina.

    English:
        RPA robot registered in Maestro.

        Each robot points to a Python script inside
        ``settings.ROBOS_SCRIPTS_DIR``. Maestro never runs an arbitrary
        path: the path is always resolved inside that folder (see
        ``robots.tasks._resolver_script``).

        ``responsavel`` uses ``on_delete=PROTECT``: a user who owns robots
        cannot be deleted before the robots are handed to someone else, so
        we never lose track of who is accountable for them.

        With ``agente`` set, the robot runs on that machine, not in the
        worker; the script path is then resolved by the agent, inside its
        own approved folder. ``PROTECT`` stops an agent that still has
        robots from being deleted: nobody finds out at run time that the
        robot lost its machine.
    """

    class Status(models.TextChoices):
        """Situação do robô.

        ``TextChoices`` guarda no banco o valor sem acento (``manutencao``) e
        mostra na tela o rótulo legível (``Manutenção``), obtido com
        ``get_status_display()``. Só robôs ``ATIVO`` podem ser disparados.

        English:
            Robot status.

            ``TextChoices`` stores the unaccented value in the database
            (``manutencao``) and shows the readable label (``Manutenção``) on
            screen, via ``get_status_display()``. Only ``ATIVO`` robots can be
            triggered.
        """

        ATIVO = "ativo", "Ativo"
        INATIVO = "inativo", "Inativo"
        MANUTENCAO = "manutencao", "Manutenção"

    nome = models.CharField(max_length=100)
    descricao = models.TextField(blank=True)
    caminho_script = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ATIVO,
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="robos",
    )
    timeout_segundos = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(10), MaxValueValidator(86_400)],
        help_text="Vazio usa o tempo máximo padrão da aba de configurações.",
    )
    max_tentativas = models.PositiveSmallIntegerField(
        default=0,
        validators=[MaxValueValidator(5)],
        help_text=(
            "De 0 a 5. Com 2, o robô roda até 3 vezes. Parada pelo usuário "
            "e script inválido não tentam de novo."
        ),
    )
    duracao_esperada_segundos = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Quanto o robô costuma levar, em segundos (opcional).",
    )
    agente = models.ForeignKey(
        "agents.Agente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="robos",
        help_text="Vazio: o robô roda no worker do Maestro.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Declara a permissão própria ``executar_robo``.

        Iniciar e parar um robô é diferente de editá-lo, por isso ganha uma
        permissão separada das padrão (``add``, ``change``, ``delete`` e
        ``view``). Na view ela é exigida como ``"robots.executar_robo"``.

        English:
            Declares the custom ``executar_robo`` permission.

            Starting and stopping a robot is different from editing it, so it
            gets its own permission besides the default ones (``add``,
            ``change``, ``delete`` and ``view``). Views require it as
            ``"robots.executar_robo"``.
        """

        permissions = [
            ("executar_robo", "Pode iniciar e parar robôs"),
        ]

    def __str__(self) -> str:
        """Retorna o nome do robô, usado no admin e nos selects.

        English:
            Returns the robot's name, used in the admin and in selects.
        """
        return self.nome
