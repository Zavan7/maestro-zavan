"""Testes do app de execuções: model e views.

English:
    Tests for the executions app: model and views.
"""
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import Client, TestCase

from executions.models import Execucao
from robots.models import Robo

User = get_user_model()


class ExecucaoModelTest(TestCase):
    """Testes do model Execucao.

    English:
        Tests for the Execucao model.
    """

    def setUp(self):
        """Cria um usuário e um robô antes de cada teste.

        English:
            Creates a user and a robot before each test.
        """
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
        """A execução fica ligada ao robô e a quem a disparou.

        English:
            The execution is linked to the robot and to whoever triggered it.
        """
        execucao = Execucao.objects.create(
            robo=self.robo,
            disparado_por=self.usuario,
        )

        self.assertEqual(execucao.robo, self.robo)
        self.assertEqual(execucao.disparado_por, self.usuario)

    def test_status_padrao_e_pendente(self):
        """Uma execução nova começa como pendente, esperando o worker.

        English:
            A new execution starts as pending, waiting for the worker.
        """
        execucao = Execucao.objects.create(robo=self.robo)

        self.assertEqual(execucao.status, Execucao.Status.PENDENTE)

    def test_str_retorna_nome_do_robo_e_status(self):
        """O __str__ junta o nome do robô e o status legível.

        English:
            __str__ combines the robot name and the readable status.
        """
        execucao = Execucao.objects.create(
            robo=self.robo,
            status=Execucao.Status.FALHA,
        )

        self.assertEqual(str(execucao), "coleta-notas-fiscais — Falha")

    def test_nao_permite_excluir_robo_com_execucoes_associadas(self):
        """Robô com execuções não pode ser excluído.

        Garante o on_delete=PROTECT: o histórico nunca some junto com o robô.

        English:
            A robot with executions cannot be deleted.

            Guarantees on_delete=PROTECT: the history never disappears along
            with the robot.
        """
        Execucao.objects.create(robo=self.robo)

        with self.assertRaises(ProtectedError):
            self.robo.delete()

    def test_excluir_usuario_mantem_execucao_com_disparado_por_nulo(self):
        """Excluir o usuário mantém a execução, só sem quem disparou.

        Garante o on_delete=SET_NULL em disparado_por.

        English:
            Deleting the user keeps the execution, minus who triggered it.

            Guarantees on_delete=SET_NULL on disparado_por.
        """
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
    """Testes das views de execuções.

    English:
        Tests for the execution views.
    """

    def setUp(self):
        """Cria usuário, robô e uma execução com log.

        English:
            Creates a user, a robot and an execution with a log.
        """
        self.client = Client()
        self.usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="/scripts/x.py",
            responsavel=self.usuario,
        )
        self.execucao = Execucao.objects.create(
            robo=self.robo, log="linha 1\nlinha 2"
        )

    def test_execution_list_redireciona_se_deslogado(self):
        """Quem não está logado é redirecionado (302) para o login.

        English:
            Anyone not logged in is redirected (302) to the login page.
        """
        response = self.client.get("/execucoes/")
        self.assertEqual(response.status_code, 302)

    def test_execution_list_retorna_200_logado(self):
        """Logado, a lista abre e mostra o robô.

        English:
            When logged in, the list opens and shows the robot.
        """
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/execucoes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "robo-teste")

    def test_execution_detail_mostra_log(self):
        """O detalhe mostra o log da execução.

        English:
            The detail page shows the execution log.
        """
        self.client.login(username="analista", password="senha123")
        response = self.client.get(f"/execucoes/{self.execucao.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "linha 1")

    def test_execution_detail_404_para_pk_inexistente(self):
        """Um id que não existe responde 404, e não erro 500.

        English:
            A nonexistent id answers 404, not a 500 error.
        """
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/execucoes/99999/")
        self.assertEqual(response.status_code, 404)

