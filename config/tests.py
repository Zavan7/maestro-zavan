from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase

from config.models import ConfiguracaoSistema

from config.models import ConfiguracaoSistema, RegistroAcesso
from config.services import AlteracaoRecusada, alternar_ativo, trocar_grupo

User = get_user_model()


class ConfiguracaoSistemaTest(TestCase):
    def test_existe_um_registro_so(self):
        primeira = ConfiguracaoSistema.atual()
        primeira.retencao_dias = 30
        primeira.save()

        ConfiguracaoSistema(retencao_dias=60).save()

        self.assertEqual(ConfiguracaoSistema.objects.count(), 1)
        self.assertEqual(ConfiguracaoSistema.atual().retencao_dias, 60)


class ConfigHomeTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_sistema = User.objects.create_user(username="admin_sistema", password="senha123")
        self.admin_sistema.groups.add(Group.objects.get(name="Administrador do sistema"))
        self.operador = User.objects.create_user(username="operador", password="senha123")
        self.operador.groups.add(Group.objects.get(name="Operador"))

    def test_redireciona_se_deslogado(self):
        response = self.client.get("/configuracoes/")
        self.assertEqual(response.status_code, 302)

    def test_operador_recebe_403(self):
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/configuracoes/")
        self.assertEqual(response.status_code, 403)

    def test_administrador_do_sistema_ve_as_secoes(self):
        self.client.login(username="admin_sistema", password="senha123")
        response = self.client.get("/configuracoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "usuários e acesso")
        self.assertContains(response, "limites padrão de execução")

    def test_menu_so_mostra_configuracoes_para_quem_tem_acesso(self):
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/robots/")
        self.assertNotContains(response, "/configuracoes/")

        self.client.login(username="admin_sistema", password="senha123")
        response = self.client.get("/robots/")
        self.assertContains(response, "/configuracoes/")

    def test_cada_secao_aparece_so_com_a_propria_permissao(self):
        observador = User.objects.create_user(username="observador", password="senha123")
        observador.user_permissions.add(
            Permission.objects.get(codename="ver_status_sistema")
        )
        self.client.login(username="observador", password="senha123")

        response = self.client.get("/configuracoes/")

        self.assertContains(response, "status do sistema")
        self.assertNotContains(response, "usuários e acesso")


class ServicosDeAcessoTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="admin_sistema", password="senha123")
        self.admin.groups.add(Group.objects.get(name="Administrador do sistema"))
        self.alvo = User.objects.create_user(username="analista", password="senha123")
        self.alvo.groups.add(Group.objects.get(name="Operador"))
        self.admin_rpa = Group.objects.get(name="Administrador RPA")

    def test_trocar_grupo_substitui_e_registra(self):
        trocar_grupo(self.admin, self.alvo, self.admin_rpa)

        self.assertEqual(list(self.alvo.groups.all()), [self.admin_rpa])
        registro = RegistroAcesso.objects.get()
        self.assertEqual(registro.autor, self.admin)
        self.assertEqual(registro.detalhe, "analista: Operador → Administrador RPA")

    def test_trocar_para_sem_grupo_remove_todos(self):
        trocar_grupo(self.admin, self.alvo, None)

        self.assertFalse(self.alvo.groups.exists())

    def test_ninguem_altera_o_proprio_acesso(self):
        with self.assertRaises(AlteracaoRecusada):
            trocar_grupo(self.admin, self.admin, None)
        with self.assertRaises(AlteracaoRecusada):
            alternar_ativo(self.admin, self.admin)

        self.assertTrue(self.admin.groups.exists())
        self.assertFalse(RegistroAcesso.objects.exists())

    def test_superusuario_so_e_alterado_por_superusuario(self):
        chefe = User.objects.create_superuser(username="chefe", password="senha123")

        with self.assertRaises(AlteracaoRecusada):
            alternar_ativo(self.admin, chefe)

        chefe.refresh_from_db()
        self.assertTrue(chefe.is_active)

    def test_desativar_e_reativar(self):
        alternar_ativo(self.admin, self.alvo)
        self.alvo.refresh_from_db()
        self.assertFalse(self.alvo.is_active)

        alternar_ativo(self.admin, self.alvo)
        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.is_active)

        acoes = list(RegistroAcesso.objects.order_by("id").values_list("acao", flat=True))
        self.assertEqual(acoes, ["desativacao", "reativacao"])

    def test_usuario_desativado_nao_consegue_entrar(self):
        alternar_ativo(self.admin, self.alvo)

        self.assertFalse(self.client.login(username="analista", password="senha123"))


class ConfigUsersViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(username="admin_sistema", password="senha123")
        self.admin.groups.add(Group.objects.get(name="Administrador do sistema"))
        self.alvo = User.objects.create_user(username="analista", password="senha123")
        self.alvo.groups.add(Group.objects.get(name="Operador"))
        self.admin_rpa = Group.objects.get(name="Administrador RPA")
        self.client.login(username="admin_sistema", password="senha123")

    def test_lista_mostra_os_usuarios(self):
        response = self.client.get("/configuracoes/usuarios/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "analista")

    def test_operador_recebe_403(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/configuracoes/usuarios/")
        self.assertEqual(response.status_code, 403)

    def test_trocar_grupo_pela_tela(self):
        response = self.client.post(
            f"/configuracoes/usuarios/{self.alvo.pk}/grupo/",
            {"grupo": self.admin_rpa.pk},
            follow=True,
        )

        self.assertEqual(list(self.alvo.groups.all()), [self.admin_rpa])
        self.assertContains(response, "Grupo de &#x27;analista&#x27; alterado.")

    def test_grupo_inexistente_responde_404(self):
        response = self.client.post(
            f"/configuracoes/usuarios/{self.alvo.pk}/grupo/", {"grupo": 9999}
        )
        self.assertEqual(response.status_code, 404)

    def test_recusa_aparece_como_mensagem(self):
        response = self.client.post(
            f"/configuracoes/usuarios/{self.admin.pk}/alternar/", follow=True
        )

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertContains(response, "não é possível alterar o próprio acesso")

    def test_desativar_pela_tela(self):
        self.client.post(f"/configuracoes/usuarios/{self.alvo.pk}/alternar/")

        self.alvo.refresh_from_db()
        self.assertFalse(self.alvo.is_active)

    def test_get_nao_altera_nada(self):
        self.client.get(f"/configuracoes/usuarios/{self.alvo.pk}/alternar/")

        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.is_active)
