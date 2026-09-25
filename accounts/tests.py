from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class LogoutTest(TestCase):
    def test_logout_encerra_sessao_e_volta_para_portfolio(self):
        User.objects.create_user(username="analista", password="senha123")
        self.client.login(username="analista", password="senha123")

        response = self.client.post("/logout/")

        self.assertRedirects(response, reverse("portfolio"))
        self.assertNotIn("_auth_user_id", self.client.session)