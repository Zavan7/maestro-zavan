from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ConfiguracaoSistema(models.Model):
    retencao_dias = models.PositiveIntegerField(
        default=90,
        validators=[MinValueValidator(7), MaxValueValidator(3650)],
        help_text="Por quantos dias guardar execuções e logs.",
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do sistema"
        default_permissions = ()
        permissions = [
            ("gerenciar_usuarios", "Pode gerenciar usuários e acesso"),
            ("ver_status_sistema", "Pode ver o status do sistema"),
            ("gerenciar_retencao", "Pode alterar a retenção do histórico"),
            ("gerenciar_limites", "Pode alterar os limites padrão de execução"),
        ]

    def __str__(self):
        return "Configuração do sistema"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def atual(cls):
        configuracao, _ = cls.objects.get_or_create(pk=1)
        return configuracao


class RegistroAcesso(models.Model):
    class Acao(models.TextChoices):
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
        ordering = ["-criado_em"]
        default_permissions = ()

    def __str__(self):
        return f"{self.get_acao_display()}: {self.detalhe}"
