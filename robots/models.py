from django.db import models
from django.conf import settings


class Robo(models.Model):
    class Status(models.TextChoices):
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
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome