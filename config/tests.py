"""Testes do app de configurações: model, serviços e views.

English:
    Tests for the settings app: model, services and views.
"""

from datetime import datetime, timedelta
from unittest import mock

import redis
from django.contrib.auth.models import Group, Permission, User
from django.test import Client, TestCase
from django.utils import timezone

from config.models import ConfiguracaoSistema, RegistroAcesso
from config.services import (
    AlteracaoRecusada,
    alternar_ativo,
    limpar_historico,
    trocar_grupo,
)
from config.status import (
    CHAVE_PULSO_AGENDADOR,
    VALIDADE_PULSO_SEGUNDOS,
    ItemStatus,
    registrar_pulso,
    status_do_sistema,
    verificar_agendador,
    verificar_redis,
    verificar_worker,
)
from config.tasks import limpar_historico_antigo
from executions.models import Execucao
from robots.models import Robo

AGORA = timezone.make_aware(datetime(2026, 10, 21, 12, 0))
STATUS_FALSO = [ItemStatus("fila (Redis)", True, "respondendo")]


def patch_status_do_sistema():
    """Troca as verificações reais por um status fixo, sem Redis.

    Sem isso, abrir a aba nos testes tentaria conectar no Redis local.

    English:
        Replaces the real checks with a fixed status, without Redis.

        Without it, opening the tab in tests would try to connect to the
        local Redis.
    """
    return mock.patch(
        "config.views.status_do_sistema", return_value=STATUS_FALSO
    )


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
        patcher = patch_status_do_sistema()
        patcher.start()
        self.addCleanup(patcher.stop)

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


class FakeRedis:
    """Redis falso em memória, só com o que o status do sistema usa.

    English:
        In-memory fake Redis, with only what the system status uses.
    """

    def __init__(self, fora_do_ar=False):
        """Cria o Redis falso, opcionalmente fora do ar.

        English:
            Creates the fake Redis, optionally down.
        """
        self.fora_do_ar = fora_do_ar
        self.dados = {}
        self.validades = {}

    def _conferir(self):
        """Levanta erro de conexão se o Redis falso estiver fora do ar.

        English:
            Raises a connection error if the fake Redis is down.
        """
        if self.fora_do_ar:
            raise redis.ConnectionError("fora do ar")

    def ping(self):
        """Responde ao ping.

        English:
            Answers the ping.
        """
        self._conferir()
        return True

    def get(self, name):
        """Lê uma chave em bytes, como o Redis real.

        English:
            Reads a key as bytes, like the real Redis.
        """
        self._conferir()
        valor = self.dados.get(name)
        return valor.encode() if valor is not None else None

    def set(self, name, value, ex=None):
        """Grava uma chave e guarda a validade.

        English:
            Writes a key and stores its expiry.
        """
        self._conferir()
        self.dados[name] = value
        self.validades[name] = ex


class StatusDoSistemaTest(TestCase):
    """Testes das verificações de Redis, worker e agendador.

    English:
        Tests for the Redis, worker and scheduler checks.
    """

    def test_redis_respondendo(self):
        """Redis que responde ao ping aparece como ok.

        English:
            A Redis that answers ping shows as ok.
        """
        self.assertTrue(verificar_redis(FakeRedis()).ok)

    def test_redis_fora_do_ar(self):
        """Redis fora do ar aparece como falha, sem levantar exceção.

        English:
            A Redis that is down shows as failed, without raising.
        """
        status = verificar_redis(FakeRedis(fora_do_ar=True))

        self.assertFalse(status.ok)
        self.assertEqual(status.detalhe, "sem resposta")

    def test_pulso_recente_indica_agendador_vivo(self):
        """Um pulso gravado há pouco indica o agendador funcionando.

        English:
            A recently written pulse means the scheduler is working.
        """
        cliente = FakeRedis()
        registrar_pulso(cliente, agora=AGORA - timedelta(seconds=40))

        status = verificar_agendador(cliente, agora=AGORA)

        self.assertTrue(status.ok)
        self.assertEqual(status.detalhe, "último sinal há 40s")

    def test_pulso_grava_com_validade(self):
        """O pulso é gravado com validade, para sumir se o agendador parar.

        English:
            The pulse is written with an expiry, so it vanishes if the
            scheduler stops.
        """
        cliente = FakeRedis()
        registrar_pulso(cliente, agora=AGORA)

        self.assertEqual(
            cliente.validades[CHAVE_PULSO_AGENDADOR], VALIDADE_PULSO_SEGUNDOS
        )

    def test_sem_pulso_indica_agendador_parado(self):
        """Sem pulso no Redis, o agendador aparece como parado.

        English:
            With no pulse in Redis, the scheduler shows as stopped.
        """
        status = verificar_agendador(FakeRedis(), agora=AGORA)

        self.assertFalse(status.ok)
        self.assertEqual(status.detalhe, "nenhum sinal recente")

    def test_pulso_velho_indica_agendador_parado(self):
        """Um pulso mais velho que a validade indica o agendador parado.

        English:
            A pulse older than the expiry means the scheduler is stopped.
        """
        cliente = FakeRedis()
        registrar_pulso(cliente, agora=AGORA - timedelta(minutes=10))

        self.assertFalse(verificar_agendador(cliente, agora=AGORA).ok)

    def test_worker_respondendo(self):
        """Com um worker respondendo ao ping, o worker aparece como ok.

        English:
            With one worker answering ping, the worker shows as ok.
        """
        with mock.patch("config.status.app.control.inspect") as inspect:
            inspect.return_value.ping.return_value = {
                "celery@maquina": {"ok": "pong"}
            }
            status = verificar_worker()

        self.assertTrue(status.ok)
        self.assertEqual(status.detalhe, "1 ativo")

    def test_nenhum_worker(self):
        """Sem resposta de nenhum worker, o worker aparece como parado.

        English:
            With no worker answering, the worker shows as stopped.
        """
        with mock.patch("config.status.app.control.inspect") as inspect:
            inspect.return_value.ping.return_value = None
            status = verificar_worker()

        self.assertFalse(status.ok)

    def test_redis_fora_nao_tenta_worker_nem_agendador(self):
        """Com o Redis fora, worker e agendador falham sem nova tentativa.

        English:
            With Redis down, worker and scheduler fail without another
            attempt.
        """
        with (
            mock.patch(
                "config.status.conectar_redis",
                return_value=FakeRedis(fora_do_ar=True),
            ),
            mock.patch("config.status.verificar_worker") as worker,
        ):
            itens = status_do_sistema()

        worker.assert_not_called()
        self.assertEqual(
            [item.nome for item in itens if not item.ok],
            ["fila (Redis)", "worker", "agendador"],
        )


class RetencaoTest(TestCase):
    """Testes da limpeza do histórico e da edição da retenção.

    English:
        Tests for history cleanup and retention editing.
    """

    def setUp(self):
        """Cria um robô, um administrador do sistema e um operador.

        English:
            Creates a robot, a system administrator and an operator.
        """
        self.admin = User.objects.create_user(
            username="admin_sistema", password="senha123"
        )
        self.admin.groups.add(
            Group.objects.get(name="Administrador do sistema")
        )
        self.operador = User.objects.create_user(
            username="operador", password="senha123"
        )
        self.operador.groups.add(Group.objects.get(name="Operador"))
        self.robo = Robo.objects.create(
            nome="coleta-notas",
            caminho_script="robo_exemplo.py",
            responsavel=self.admin,
        )
        configuracao = ConfiguracaoSistema.atual()
        configuracao.retencao_dias = 30
        configuracao.save()

    def _execucao(self, status, dias_atras):
        """Cria uma execução finalizada há ``dias_atras`` dias.

        English:
            Creates an execution finished ``dias_atras`` days ago.
        """
        return Execucao.objects.create(
            robo=self.robo,
            status=status,
            finalizado_em=AGORA - timedelta(days=dias_atras),
        )

    def test_apaga_so_finalizadas_mais_antigas_que_a_retencao(self):
        """Só execuções finalizadas antes do limite são apagadas.

        English:
            Only executions finished before the limit are deleted.
        """
        antiga_ok = self._execucao(Execucao.Status.SUCESSO, 31)
        antiga_falha = self._execucao(Execucao.Status.FALHA, 90)
        self._execucao(Execucao.Status.CANCELADA, 45)
        recente = self._execucao(Execucao.Status.SUCESSO, 29)

        apagadas = limpar_historico(agora=AGORA)

        self.assertEqual(apagadas, 3)
        restantes = set(Execucao.objects.values_list("pk", flat=True))
        self.assertEqual(restantes, {recente.pk})
        self.assertNotIn(antiga_ok.pk, restantes)
        self.assertNotIn(antiga_falha.pk, restantes)

    def test_nunca_apaga_pendente_ou_rodando(self):
        """Execuções em andamento ficam, por mais antigas que sejam.

        English:
            Executions in progress stay, however old they are.
        """
        self._execucao(Execucao.Status.PENDENTE, 365)
        self._execucao(Execucao.Status.RODANDO, 365)
        Execucao.objects.create(robo=self.robo)

        self.assertEqual(limpar_historico(agora=AGORA), 0)
        self.assertEqual(Execucao.objects.count(), 3)

    def test_tarefa_devolve_a_quantidade_apagada(self):
        """A tarefa do beat chama a limpeza e devolve quantas apagou.

        English:
            The beat task runs the cleanup and returns how many it deleted.
        """
        self._execucao(Execucao.Status.SUCESSO, 400)

        self.assertEqual(limpar_historico_antigo(), 1)

    def test_salvar_retencao_pela_tela(self):
        """Um valor válido é salvo e confirmado com mensagem.

        English:
            A valid value is saved and confirmed with a message.
        """
        self.client.login(username="admin_sistema", password="senha123")

        with patch_status_do_sistema():
            response = self.client.post(
                "/configuracoes/retencao/",
                {"retencao_dias": 60},
                follow=True,
            )

        self.assertEqual(ConfiguracaoSistema.atual().retencao_dias, 60)
        self.assertContains(response, "Retenção salva: 60 dias.")

    def test_valor_fora_do_limite_mostra_erro(self):
        """Um valor abaixo do mínimo não é salvo e a aba mostra o erro.

        English:
            A value below the minimum is not saved and the tab shows the
            error.
        """
        self.client.login(username="admin_sistema", password="senha123")

        with patch_status_do_sistema():
            response = self.client.post(
                "/configuracoes/retencao/", {"retencao_dias": 1}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ConfiguracaoSistema.atual().retencao_dias, 30)
        self.assertContains(response, "Retenção não salva")

    def test_operador_recebe_403(self):
        """Sem gerenciar_retencao, salvar a retenção responde 403.

        English:
            Without gerenciar_retencao, saving the retention answers 403.
        """
        self.client.login(username="operador", password="senha123")

        response = self.client.post(
            "/configuracoes/retencao/", {"retencao_dias": 60}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ConfiguracaoSistema.atual().retencao_dias, 30)

    def test_get_nao_altera_nada(self):
        """Um GET só volta para a aba, sem alterar a retenção.

        English:
            A GET just goes back to the tab, without changing retention.
        """
        self.client.login(username="admin_sistema", password="senha123")

        response = self.client.get(
            "/configuracoes/retencao/", {"retencao_dias": 60}
        )

        self.assertRedirects(
            response, "/configuracoes/", fetch_redirect_response=False
        )
        self.assertEqual(ConfiguracaoSistema.atual().retencao_dias, 30)


class CriarUsuarioTest(TestCase):
    """Testes da criação de usuários pela aba de configurações.

    English:
        Tests for creating users through the settings tab.
    """

    URL = "/configuracoes/usuarios/novo/"

    def setUp(self):
        """Cria um administrador do sistema e já faz login com ele.

        English:
            Creates a system administrator and logs in as them.
        """
        self.admin = User.objects.create_user(
            username="admin_sistema", password="senha123"
        )
        self.admin.groups.add(
            Group.objects.get(name="Administrador do sistema")
        )
        self.operador = Group.objects.get(name="Operador")
        self.client.login(username="admin_sistema", password="senha123")

    def _dados(self, **extras):
        """Monta um POST válido, com a possibilidade de trocar campos.

        English:
            Builds a valid POST, allowing fields to be overridden.
        """
        dados = {
            "username": "analista",
            "first_name": "Ana",
            "last_name": "Lima",
            "email": "ana@exemplo.com",
            "password1": "Maestro#2026x",
            "password2": "Maestro#2026x",
            "grupo": self.operador.pk,
        }
        dados.update(extras)
        return dados

    def test_formulario_abre(self):
        """O formulário de novo usuário abre para quem tem a permissão.

        English:
            The new user form opens for users with the permission.
        """
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "criar usuário")

    def test_cria_com_grupo_e_registra(self):
        """O usuário é criado com o grupo, a senha em hash e o registro.

        English:
            The user is created with the group, a hashed password and the
            record.
        """
        response = self.client.post(self.URL, self._dados(), follow=True)

        novo = User.objects.get(username="analista")
        self.assertEqual(list(novo.groups.all()), [self.operador])
        self.assertTrue(novo.check_password("Maestro#2026x"))
        self.assertFalse(novo.is_superuser)
        self.assertFalse(novo.is_staff)
        registro = RegistroAcesso.objects.get()
        self.assertEqual(registro.acao, RegistroAcesso.Acao.CRIACAO)
        self.assertEqual(registro.autor, self.admin)
        self.assertEqual(registro.detalhe, "analista (Operador)")
        self.assertContains(response, "Usuário &#x27;analista&#x27; criado.")

    def test_cria_sem_grupo(self):
        """Deixar o grupo vazio cria o usuário sem grupo.

        English:
            Leaving the group empty creates the user without a group.
        """
        self.client.post(self.URL, self._dados(grupo=""))

        novo = User.objects.get(username="analista")
        self.assertFalse(novo.groups.exists())

    def test_senhas_diferentes_nao_criam(self):
        """Com as senhas diferentes, nada é criado e o erro aparece.

        English:
            With mismatched passwords, nothing is created and the error
            shows.
        """
        response = self.client.post(
            self.URL, self._dados(password2="outra-senha-123")
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="analista").exists())
        self.assertFalse(RegistroAcesso.objects.exists())

    def test_usuario_repetido_nao_cria(self):
        """Um nome de usuário já usado é recusado pelo formulário.

        English:
            A username already in use is refused by the form.
        """
        self.client.post(self.URL, self._dados(username="admin_sistema"))

        self.assertEqual(
            User.objects.filter(username="admin_sistema").count(), 1
        )

    def test_operador_recebe_403(self):
        """Sem gerenciar_usuarios, a página responde 403.

        English:
            Without gerenciar_usuarios, the page answers 403.
        """
        operador = User.objects.create_user(
            username="operador", password="senha123"
        )
        operador.groups.add(self.operador)
        self.client.login(username="operador", password="senha123")

        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_deslogado_vai_para_o_login(self):
        """Quem não está logado é redirecionado para o login.

        English:
            Anyone not logged in is redirected to the login page.
        """
        self.client.logout()

        self.assertEqual(self.client.get(self.URL).status_code, 302)


class LimitesPadraoTest(TestCase):
    """Testes da edição dos limites padrão de execução.

    English:
        Tests for editing the default execution limits.
    """

    URL = "/configuracoes/limites/"

    def setUp(self):
        """Cria um administrador do sistema e um operador.

        English:
            Creates a system administrator and an operator.
        """
        self.admin = User.objects.create_user(
            username="admin_sistema", password="senha123"
        )
        self.admin.groups.add(
            Group.objects.get(name="Administrador do sistema")
        )
        operador = User.objects.create_user(
            username="operador", password="senha123"
        )
        operador.groups.add(Group.objects.get(name="Operador"))

    def test_salva_os_limites(self):
        """Valores válidos são salvos e confirmados com mensagem.

        English:
            Valid values are saved and confirmed with a message.
        """
        self.client.login(username="admin_sistema", password="senha123")

        with patch_status_do_sistema():
            response = self.client.post(
                self.URL,
                {"timeout_padrao_segundos": 600, "limite_log": 20_000},
                follow=True,
            )

        configuracao = ConfiguracaoSistema.atual()
        self.assertEqual(configuracao.timeout_padrao_segundos, 600)
        self.assertEqual(configuracao.limite_log, 20_000)
        self.assertContains(response, "Limites padrão salvos.")

    def test_valor_fora_do_limite_mostra_erro(self):
        """Um tempo abaixo do mínimo não é salvo e a aba mostra o erro.

        English:
            A time below the minimum is not saved and the tab shows the
            error.
        """
        self.client.login(username="admin_sistema", password="senha123")

        with patch_status_do_sistema():
            response = self.client.post(
                self.URL,
                {"timeout_padrao_segundos": 1, "limite_log": 20_000},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Limites não salvos")
        self.assertEqual(
            ConfiguracaoSistema.atual().timeout_padrao_segundos, 300
        )

    def test_operador_recebe_403(self):
        """Sem gerenciar_limites, salvar os limites responde 403.

        English:
            Without gerenciar_limites, saving the limits answers 403.
        """
        self.client.login(username="operador", password="senha123")

        response = self.client.post(
            self.URL, {"timeout_padrao_segundos": 600, "limite_log": 20_000}
        )

        self.assertEqual(response.status_code, 403)

    def test_deslogado_vai_para_o_login(self):
        """Quem não está logado é redirecionado para o login.

        English:
            Anyone not logged in is redirected to the login page.
        """
        response = self.client.post(self.URL, {})

        self.assertEqual(response.status_code, 302)
