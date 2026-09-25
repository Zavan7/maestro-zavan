from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase, Client
from executions.models import Execucao
from robots.models import Robo

User = get_user_model()


class ExecucaoModelTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username="analista_rpa",
            password="senha-de-teste-123",
        )
        self.robo = Robo.objects.create(
            nome="coleta-notas-fiscais",
            caminho_script="/scripts/coleta_notas.py",
            responsavel=self.usuario,
        )

    def test_criacao_execucao_ligada_ao_robo(self):
        execucao = Execucao.objects.create(
            robo=self.robo,
            disparado_por=self.usuario,
        )

        self.assertEqual(execucao.robo, self.robo)
        self.assertEqual(execucao.disparado_por, self.usuario)

    def test_status_padrao_e_pendente(self):
        execucao = Execucao.objects.create(robo=self.robo)

        self.assertEqual(execucao.status, Execucao.Status.PENDENTE)

    def test_str_retorna_nome_do_robo_e_status(self):
        execucao = Execucao.objects.create(
            robo=self.robo,
            status=Execucao.Status.FALHA,
        )

        self.assertEqual(str(execucao), "coleta-notas-fiscais — Falha")

    def test_nao_permite_excluir_robo_com_execucoes_associadas(self):
        Execucao.objects.create(robo=self.robo)

        with self.assertRaises(ProtectedError):
            self.robo.delete()

    def test_excluir_usuario_mantem_execucao_com_disparado_por_nulo(self):
        outro_usuario = User.objects.create_user(
            username="quem_so_dispara",
            password="senha-de-teste-123",
        )
        execucao = Execucao.objects.create(
            robo=self.robo,
            disparado_por=outro_usuario,
        )

        outro_usuario.delete()
        execucao.refresh_from_db()

        self.assertIsNone(execucao.disparado_por)


class ExecutionViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="/scripts/x.py",
            responsavel=self.usuario
        )
        self.execucao = Execucao.objects.create(
            robo=self.robo, log="linha 1\nlinha 2"
        )

    def test_execution_list_redireciona_se_deslogado(self):
        response = self.client.get("/execucoes/")
        self.assertEqual(response.status_code, 302)

    def test_execution_list_retorna_200_logado(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/execucoes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "robo-teste")

    def test_execution_detail_mostra_log(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get(f"/execucoes/{self.execucao.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "linha 1")

    def test_execution_detail_404_para_pk_inexistente(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/execucoes/99999/")
        self.assertEqual(response.status_code, 404)

