"""Testes do app de contas.

English:
    Tests for the accounts app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from agents.models import Agente

User = get_user_model()


class LogoutTest(TestCase):
    """Testes do logout.

    English:
        Logout tests.
    """

    def test_logout_encerra_sessao_e_volta_para_portfolio(self):
        """O logout via POST limpa a sessão e leva à página pública.

        Desde o Django 5 o logout só aceita POST, para que um link ou imagem
        maliciosa não consiga deslogar o usuário.

        English:
            Logging out via POST clears the session and opens the public page.

            Since Django 5, logout only accepts POST, so a malicious link or
            image cannot log the user out.
        """
        User.objects.create_user(username="analista", password="senha123")
        self.client.login(username="analista", password="senha123")

        response = self.client.post("/logout/")

        self.assertRedirects(response, reverse("portfolio"))
        self.assertNotIn("_auth_user_id", self.client.session)


class PainelAgentesTest(TestCase):
    """Testes do painel de agentes na tela inicial.

    English:
        Tests for the agents panel on the home page.
    """

    def setUp(self) -> None:
        """Cria um usuário comum logado.

        English:
            Creates a regular logged-in user.
        """
        self.usuario = User.objects.create_user(
            username="operador", password="senha123"
        )
        self.client.login(username="operador", password="senha123")

    def test_mostra_agente_online_e_offline(self) -> None:
        """Agente com sinal recente aparece online; o antigo, offline.

        English:
            An agent with a recent signal shows online; an old one,
            offline.
        """
        agora = timezone.now()
        Agente.objects.create(
            nome="servidor-online", token_hash="a" * 64, ultimo_sinal=agora
        )
        Agente.objects.create(
            nome="servidor-offline",
            token_hash="b" * 64,
            ultimo_sinal=agora - timedelta(hours=1),
        )

        response = self.client.get(reverse("home"))

        linhas = {
            linha.nome: linha.online for linha in response.context["agentes"]
        }
        self.assertEqual(
            linhas, {"servidor-online": True, "servidor-offline": False}
        )
        self.assertEqual(
            response.context["agentes"][0].nome, "servidor-online"
        )
        self.assertContains(response, "offline há")

    def test_agente_desativado_nao_aparece(self) -> None:
        """Agente desativado fica fora do painel.

        English:
            A deactivated agent stays off the dashboard.
        """
        Agente.objects.create(
            nome="aposentado", token_hash="c" * 64, ativo=False
        )

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "aposentado")
        self.assertContains(response, "Nenhum agente ativo")

    def test_link_de_gerenciar_so_com_permissao(self) -> None:
        """O link para gerenciar agentes depende da permissão.

        English:
            The link to manage agents depends on the permission.
        """
        url_agentes = reverse("agent_list")

        response = self.client.get(reverse("home"))
        self.assertNotContains(response, url_agentes)

        self.usuario.user_permissions.add(
            Permission.objects.get(codename="gerenciar_agentes")
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, url_agentes)
