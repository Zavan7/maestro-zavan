from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from robots.models import Robo

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