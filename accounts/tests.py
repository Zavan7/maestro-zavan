"""Testes do app de contas.

English:
    Tests for the accounts app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
