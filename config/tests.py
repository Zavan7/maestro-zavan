"""Testes do app de configurações: model, serviços e views.

English:
    Tests for the settings app: model, services and views.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase

from config.models import ConfiguracaoSistema, RegistroAcesso
from config.services import AlteracaoRecusada, alternar_ativo, trocar_grupo

User = get_user_model()


class ConfiguracaoSistemaTest(TestCase):
    """Testes do registro único de configuração.

    English:
        Tests for the single settings record.
    """

    def test_existe_um_registro_so(self):
        """Salvar uma instância nova sobrescreve o mesmo registro (pk=1).

        English:
            Saving a new instance overwrites the same record (pk=1).
        """
        primeira = ConfiguracaoSistema.atual()
        primeira.retencao_dias = 30
        primeira.save()

        ConfiguracaoSistema(retencao_dias=60).save()

        self.assertEqual(ConfiguracaoSistema.objects.count(), 1)
        self.assertEqual(ConfiguracaoSistema.atual().retencao_dias, 60)


class ConfigHomeTest(TestCase):
    """Testes da página inicial de configurações.

    English:
        Tests for the settings home page.
    """

    def setUp(self):
        """Cria um administrador do sistema e um operador.

        English:
            Creates a system administrator and an operator.
        """
        self.client = Client()
        self.admin_sistema = User.objects.create_user(
            username="admin_sistema", password="senha123"
        )
        self.admin_sistema.groups.add(
            Group.objects.get(name="Administrador do sistema")
        )
        self.operador = User.objects.create_user(
            username="operador", password="senha123"
        )
        self.operador.groups.add(Group.objects.get(name="Operador"))

    def test_redireciona_se_deslogado(self):
        """Quem não está logado é redirecionado (302) para o login.

        English:
            Anyone not logged in is redirected (302) to the login page.
        """
        response = self.client.get("/configuracoes/")
        self.assertEqual(response.status_code, 302)

    def test_operador_recebe_403(self):
        """Operador, sem nenhuma permissão do app, recebe 403.

        English:
            An operator, with no permission in the app, gets 403.
        """
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/configuracoes/")
        self.assertEqual(response.status_code, 403)

    def test_administrador_do_sistema_ve_as_secoes(self):
        """O administrador do sistema vê as seções da aba.

        English:
            The system administrator sees the tab sections.
        """
        self.client.login(username="admin_sistema", password="senha123")
        response = self.client.get("/configuracoes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "usuários e acesso")
        self.assertContains(response, "limites padrão de execução")

    def test_menu_so_mostra_configuracoes_para_quem_tem_acesso(self):
        """O link de configurações no menu só aparece para quem tem acesso.

        English:
            The settings link in the menu only appears for users with access.
        """
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/robots/")
        self.assertNotContains(response, "/configuracoes/")

        self.client.login(username="admin_sistema", password="senha123")
        response = self.client.get("/robots/")
        self.assertContains(response, "/configuracoes/")

    def test_cada_secao_aparece_so_com_a_propria_permissao(self):
        """Cada seção depende da própria permissão, e não de um acesso geral.

        English:
            Each section depends on its own permission, not on general access.
        """
        observador = User.objects.create_user(
            username="observador", password="senha123"
        )
        observador.user_permissions.add(
            Permission.objects.get(codename="ver_status_sistema")
        )
        self.client.login(username="observador", password="senha123")

        response = self.client.get("/configuracoes/")

        self.assertContains(response, "status do sistema")
        self.assertNotContains(response, "usuários e acesso")


class ServicosDeAcessoTest(TestCase):
    """Testes dos serviços de gestão de acesso.

    English:
        Tests for the access management services.
    """

    def setUp(self):
        """Cria um administrador, um usuário alvo e o grupo de destino.

        English:
            Creates an administrator, a target user and the destination group.
        """
        self.admin = User.objects.create_user(
            username="admin_sistema", password="senha123"
        )
        self.admin.groups.add(
            Group.objects.get(name="Administrador do sistema")
        )
        self.alvo = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.alvo.groups.add(Group.objects.get(name="Operador"))
        self.admin_rpa = Group.objects.get(name="Administrador RPA")

    def test_trocar_grupo_substitui_e_registra(self):
        """Trocar o grupo substitui o atual e grava o registro de auditoria.

        English:
            Changing the group replaces the current one and writes the audit
            record.
        """
        trocar_grupo(self.admin, self.alvo, self.admin_rpa)

        self.assertEqual(list(self.alvo.groups.all()), [self.admin_rpa])
        registro = RegistroAcesso.objects.get()
        self.assertEqual(registro.autor, self.admin)
        self.assertEqual(
            registro.detalhe, "analista: Operador → Administrador RPA"
        )

    def test_trocar_para_sem_grupo_remove_todos(self):
        """Trocar para nenhum grupo remove todos os grupos do usuário.

        English:
            Changing to no group removes all of the user's groups.
        """
        trocar_grupo(self.admin, self.alvo, None)

        self.assertFalse(self.alvo.groups.exists())

    def test_ninguem_altera_o_proprio_acesso(self):
        """Ninguém troca o próprio grupo nem desativa a si mesmo.

        Também confere que, recusada a alteração, nada foi gravado.

        English:
            Nobody changes their own group or deactivates themselves.

            It also checks that, once refused, nothing was saved.
        """
        with self.assertRaises(AlteracaoRecusada):
            trocar_grupo(self.admin, self.admin, None)
        with self.assertRaises(AlteracaoRecusada):
            alternar_ativo(self.admin, self.admin)

        self.assertTrue(self.admin.groups.exists())
        self.assertFalse(RegistroAcesso.objects.exists())

    def test_superusuario_so_e_alterado_por_superusuario(self):
        """Só um superusuário pode alterar outro superusuário.

        English:
            Only a superuser can change another superuser.
        """
        chefe = User.objects.create_superuser(
            username="chefe", password="senha123"
        )

        with self.assertRaises(AlteracaoRecusada):
            alternar_ativo(self.admin, chefe)

        chefe.refresh_from_db()
        self.assertTrue(chefe.is_active)

    def test_desativar_e_reativar(self):
        """Alternar duas vezes desativa e reativa, registrando as duas ações.

        English:
            Toggling twice deactivates and reactivates, recording both actions.
        """
        alternar_ativo(self.admin, self.alvo)
        self.alvo.refresh_from_db()
        self.assertFalse(self.alvo.is_active)

        alternar_ativo(self.admin, self.alvo)
        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.is_active)

        acoes = list(
            RegistroAcesso.objects.order_by("id").values_list(
                "acao", flat=True
            )
        )
        self.assertEqual(acoes, ["desativacao", "reativacao"])

    def test_usuario_desativado_nao_consegue_entrar(self):
        """Um usuário desativado não consegue mais fazer login.

        English:
            A deactivated user can no longer log in.
        """
        alternar_ativo(self.admin, self.alvo)

        self.assertFalse(
            self.client.login(username="analista", password="senha123")
        )


class ConfigUsersViewsTest(TestCase):
    """Testes das views de gestão de usuários.

    English:
        Tests for the user management views.
    """

    def setUp(self):
        """Cria administrador e alvo e já faz login como administrador.

        English:
            Creates an administrator and a target, and logs in as the
            administrator.
        """
        self.client = Client()
        self.admin = User.objects.create_user(
            username="admin_sistema", password="senha123"
        )
        self.admin.groups.add(
            Group.objects.get(name="Administrador do sistema")
        )
        self.alvo = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.alvo.groups.add(Group.objects.get(name="Operador"))
        self.admin_rpa = Group.objects.get(name="Administrador RPA")
        self.client.login(username="admin_sistema", password="senha123")

    def test_lista_mostra_os_usuarios(self):
        """A lista mostra os usuários cadastrados.

        English:
            The list shows the registered users.
        """
        response = self.client.get("/configuracoes/usuarios/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "analista")

    def test_operador_recebe_403(self):
        """Operador sem a permissão gerenciar_usuarios recebe 403.

        English:
            An operator without the gerenciar_usuarios permission gets 403.
        """
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/configuracoes/usuarios/")
        self.assertEqual(response.status_code, 403)

    def test_trocar_grupo_pela_tela(self):
        """Trocar o grupo pela tela altera o usuário e mostra a mensagem.

        As aspas aparecem como &#x27; porque o Django escapa o HTML das
        mensagens.

        English:
            Changing the group on the page updates the user, showing a message.

            The quotes show up as &#x27; because Django escapes HTML in
            messages.
        """
        response = self.client.post(
            f"/configuracoes/usuarios/{self.alvo.pk}/grupo/",
            {"grupo": self.admin_rpa.pk},
            follow=True,
        )

        self.assertEqual(list(self.alvo.groups.all()), [self.admin_rpa])
        self.assertContains(
            response, "Grupo de &#x27;analista&#x27; alterado."
        )

    def test_grupo_inexistente_responde_404(self):
        """Um id de grupo que não existe responde 404.

        English:
            A group id that does not exist answers 404.
        """
        response = self.client.post(
            f"/configuracoes/usuarios/{self.alvo.pk}/grupo/", {"grupo": 9999}
        )
        self.assertEqual(response.status_code, 404)

    def test_recusa_aparece_como_mensagem(self):
        """A recusa do serviço vira uma mensagem de erro na tela.

        English:
            The service refusal becomes an error message on the page.
        """
        response = self.client.post(
            f"/configuracoes/usuarios/{self.admin.pk}/alternar/", follow=True
        )

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertContains(
            response, "não é possível alterar o próprio acesso"
        )

    def test_desativar_pela_tela(self):
        """Alternar pela tela desativa o usuário.

        English:
            Toggling through the page deactivates the user.
        """
        self.client.post(f"/configuracoes/usuarios/{self.alvo.pk}/alternar/")

        self.alvo.refresh_from_db()
        self.assertFalse(self.alvo.is_active)

    def test_get_nao_altera_nada(self):
        """Um GET não altera nada.

        Ações que mudam dados só podem acontecer em POST, porque um GET
        pode ser disparado sem o usuário clicar (imagem, pré-carregamento,
        robô de busca).

        English:
            A GET changes nothing.

            Actions that change data must only happen on POST, because a
            GET can fire without the user clicking (image, prefetch,
            search crawler).
        """
        self.client.get(f"/configuracoes/usuarios/{self.alvo.pk}/alternar/")

        self.alvo.refresh_from_db()
        self.assertTrue(self.alvo.is_active)
