from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase, Client
from robots.models import Robo
from executions.models import Execucao

User = get_user_model()


class RoboModelTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user(
            username="analista_rpa",
            password="senha-de-teste-123",
        )

    def test_criacao_robo_com_campos_esperados(self):
        robo = Robo.objects.create(
            nome="coleta-notas-fiscais",
            descricao="Coleta notas fiscais do portal X",
            caminho_script="/scripts/coleta_notas.py",
            responsavel=self.usuario,
        )

        self.assertEqual(robo.nome, "coleta-notas-fiscais")
        self.assertEqual(robo.responsavel, self.usuario)

    def test_status_padrao_e_ativo(self):
        robo = Robo.objects.create(
            nome="robo-sem-status-explicito",
            caminho_script="/scripts/x.py",
            responsavel=self.usuario,
        )

        self.assertEqual(robo.status, Robo.Status.ATIVO)

    def test_get_status_display_retorna_texto_legivel(self):
        robo = Robo.objects.create(
            nome="robo-manutencao",
            caminho_script="/scripts/y.py",
            responsavel=self.usuario,
            status=Robo.Status.MANUTENCAO,
        )

        self.assertEqual(robo.get_status_display(), "Manutenção")

    def test_str_retorna_nome_do_robo(self):
        robo = Robo.objects.create(
            nome="robo-com-nome-legivel",
            caminho_script="/scripts/z.py",
            responsavel=self.usuario,
        )

        self.assertEqual(str(robo), "robo-com-nome-legivel")

    def test_nao_permite_excluir_usuario_com_robos_associados(self):
        Robo.objects.create(
            nome="robo-protegido",
            caminho_script="/scripts/protegido.py",
            responsavel=self.usuario,
        )

        with self.assertRaises(ProtectedError):
            self.usuario.delete()


class RobotViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.usuario = User.objects.create_user(username="analista", password="senha123")
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="/scripts/teste.py",
            responsavel=self.usuario,
        )

    def test_robot_list_redireciona_se_deslogado(self):
        response = self.client.get("/robots/")
        self.assertEqual(response.status_code, 302)

    def test_robot_list_retorna_200_logado(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/robots/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "robo-teste")

    def test_robot_edit_salva_alteracoes(self):
        self.client.login(username="analista", password="senha123")
        self.client.post(f"/robots/{self.robo.pk}/editar/", {
            "nome": "robo-renomeado",
            "caminho_script": self.robo.caminho_script,
            "descricao": "",
            "status": "ativo",
        })
        self.robo.refresh_from_db()
        self.assertEqual(self.robo.nome, "robo-renomeado")

    def test_robot_exclusion_falha_com_execucao_associada(self):
        Execucao.objects.create(robo=self.robo)
        self.client.login(username="analista", password="senha123")
        response = self.client.post(f"/robots/{self.robo.pk}/excluir/", follow=True)
        self.assertTrue(Robo.objects.filter(pk=self.robo.pk).exists())
        self.assertContains(response, "Não é possível excluir")

    def test_robot_exclusion_funciona_sem_execucao(self):
        self.client.login(username="analista", password="senha123")
        self.client.post(f"/robots/{self.robo.pk}/excluir/")
        self.assertFalse(Robo.objects.filter(pk=self.robo.pk).exists())