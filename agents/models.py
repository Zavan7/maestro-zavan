"""Models do app de agentes.

English:
    Models for the agents app.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

PREFIXO_DO_TOKEN = "mae_"
TOLERANCIA_DO_SINAL = timedelta(seconds=90)


def hash_do_token(token: str) -> str:
    """Calcula o hash SHA-256 de um token de agente.

    O token é aleatório e longo (``secrets.token_urlsafe(32)``, 256
    bits), então um hash rápido como o SHA-256 basta: não existe lista de
    senhas comuns para testar contra ele. O banco guarda só o hash; quem
    ler o banco não consegue se passar por um agente.

    Args:
        token: token em texto, como o agente o envia.

    Returns:
        O hash em hexadecimal (64 caracteres).

    English:
        Computes the SHA-256 hash of an agent token.

        The token is random and long (``secrets.token_urlsafe(32)``, 256
        bits), so a fast hash such as SHA-256 is enough: there is no list
        of common passwords to try against it. The database stores only
        the hash; whoever reads the database cannot pose as an agent.

        Args:
            token: plain token, as the agent sends it.

        Returns:
            The hex hash (64 characters).
    """
    return hashlib.sha256(token.encode()).hexdigest()


class Agente(models.Model):
    """Máquina onde robôs rodam, conectada ao Maestro por WebSocket.

    O agente (um programa em Go, instalado na máquina) abre a conexão com
    o Maestro, se identifica pelo token e recebe os comandos de iniciar e
    parar. ``ultimo_sinal`` é atualizado a cada heartbeat; o agente é
    considerado online enquanto o último sinal for recente.

    Agentes não são excluídos pela tela: para aposentar um, desative-o.
    Um robô aponta para o agente com ``PROTECT``.

    English:
        Machine where robots run, connected to Maestro over WebSocket.

        The agent (a Go program installed on the machine) opens the
        connection to Maestro, identifies itself with the token and
        receives the start and stop commands. ``ultimo_sinal`` is updated
        on every heartbeat; the agent counts as online while the last
        signal is recent.

        Agents are not deleted through the page: to retire one, deactivate
        it. A robot points to its agent with ``PROTECT``.
    """

    nome = models.CharField(max_length=60, unique=True)
    token_hash = models.CharField(max_length=64, unique=True)
    ativo = models.BooleanField(default=True)
    ultimo_sinal = models.DateTimeField(null=True, blank=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="agentes_criados",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Ordena por nome e desliga as permissões padrão.

        Quem cadastra agentes é a aba de configurações, com a permissão
        ``config.gerenciar_agentes``.

        English:
            Orders by name and turns off the default permissions.

            Agents are registered through the settings tab, with the
            ``config.gerenciar_agentes`` permission.
        """

        ordering = ["nome"]
        default_permissions = ()

    def __str__(self) -> str:
        """Retorna o nome do agente.

        English:
            Returns the agent's name.
        """
        return self.nome

    def novo_token(self) -> str:
        """Gera um token novo, guarda só o hash e devolve o token.

        O token antigo deixa de valer na hora. O que é devolvido aqui é a
        única vez em que o token aparece: ele não fica em lugar nenhum.
        Quem chama precisa salvar o agente.

        Returns:
            O token em texto, para ser mostrado uma vez.

        English:
            Generates a new token, stores only the hash and returns the
            token.

            The old token stops working right away. What is returned here
            is the only time the token shows up: it is not kept anywhere.
            The caller must save the agent.

            Returns:
                The plain token, to be shown once.
        """
        token = PREFIXO_DO_TOKEN + secrets.token_urlsafe(32)
        self.token_hash = hash_do_token(token)
        return token

    def online(self, agora: datetime | None = None) -> bool:
        """Indica se o agente está ativo e deu sinal há pouco.

        Args:
            agora: momento de referência; ``None`` usa a hora atual.

        Returns:
            ``True`` se o último sinal está dentro da tolerância.

        English:
            Tells whether the agent is active and signalled recently.

            Args:
                agora: reference moment; ``None`` uses the current time.

            Returns:
                ``True`` if the last signal is within the tolerance.
        """
        if not self.ativo or self.ultimo_sinal is None:
            return False
        agora = agora or timezone.now()
        return agora - self.ultimo_sinal <= TOLERANCIA_DO_SINAL
