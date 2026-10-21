"""Testes do app de execuções: model e views.

English:
    Tests for the executions app: model and views.
"""

from unittest import mock

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.urls import path

from executions.ao_vivo import publicar_fim, publicar_linhas
from executions.consumers import ExecucaoConsumer
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


class LogAoVivoViewTest(TestCase):
    """Testes da tela de detalhe com o log ao vivo.

    English:
        Tests for the detail page with the live log.
    """

    def setUp(self):
        """Cria usuário, robô e faz login.

        English:
            Creates a user and a robot, and logs in.
        """
        self.usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="robo.py",
            responsavel=self.usuario,
        )
        self.client.login(username="analista", password="senha123")

    def test_rodando_abre_o_websocket(self):
        """Uma execução rodando carrega o script e o endereço do WebSocket.

        English:
            A running execution loads the script and the WebSocket address.
        """
        execucao = Execucao.objects.create(
            robo=self.robo, status=Execucao.Status.RODANDO
        )

        response = self.client.get(f"/execucoes/{execucao.pk}/")

        self.assertContains(response, f"/ws/execucoes/{execucao.pk}/")
        self.assertContains(response, "execucao-ao-vivo.js")
        self.assertNotContains(response, 'http-equiv="refresh"')

    def test_finalizada_nao_abre_o_websocket(self):
        """Uma execução finalizada não carrega o log ao vivo.

        English:
            A finished execution does not load the live log.
        """
        execucao = Execucao.objects.create(
            robo=self.robo, status=Execucao.Status.SUCESSO, log="ok"
        )

        response = self.client.get(f"/execucoes/{execucao.pk}/")

        self.assertNotContains(response, "/ws/execucoes/")
        self.assertNotContains(response, "execucao-ao-vivo.js")

    def test_numeracao_continua_quando_o_comeco_foi_cortado(self):
        """Com o começo cortado, a lista começa no número certo.

        English:
            With the start cut off, the list starts at the right number.
        """
        execucao = Execucao.objects.create(
            robo=self.robo,
            status=Execucao.Status.RODANDO,
            log="linha 99\nlinha 100",
            total_linhas=100,
        )

        response = self.client.get(f"/execucoes/{execucao.pk}/")

        self.assertContains(response, 'start="99"')
        self.assertContains(response, 'data-ultima-linha="100"')


class ExecucaoConsumerTest(TestCase):
    """Testes do WebSocket que leva o log ao navegador.

    O ``WebsocketCommunicator`` conversa com o consumer sem servidor. O
    consumer é montado sem as proteções do navegador, e o usuário é posto
    direto no ``scope``, no lugar do que o ``AuthMiddlewareStack`` leria
    da sessão. Nos testes, a camada de
    canais é a em memória.

    English:
        Tests for the WebSocket that carries the log to the browser.

        ``WebsocketCommunicator`` talks to the consumer without a server.
        The consumer is mounted without the browser protections, and the
        user is put straight into the ``scope``, instead of what
        ``AuthMiddlewareStack`` would read from the session. In tests, the
        channel layer is the in-memory one.
    """

    def setUp(self):
        """Cria usuário, robô e uma execução rodando.

        English:
            Creates a user, a robot and a running execution.
        """
        self.usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="robo.py",
            responsavel=self.usuario,
        )
        self.execucao = Execucao.objects.create(
            robo=robo, status=Execucao.Status.RODANDO
        )

    def _comunicador(self, usuario, pk=None):
        """Monta o comunicador para a execução, com o usuário no scope.

        English:
            Builds the communicator for the execution, with the user in
            the scope.
        """
        comunicador = WebsocketCommunicator(
            URLRouter(
                [path("ws/execucoes/<int:pk>/", ExecucaoConsumer.as_asgi())]
            ),
            f"/ws/execucoes/{pk or self.execucao.pk}/",
        )
        comunicador.scope["user"] = usuario
        return comunicador

    async def test_recusa_quem_nao_esta_logado(self):
        """Sem login, a conexão é recusada com o código 4401.

        English:
            Without login, the connection is refused with code 4401.
        """
        comunicador = self._comunicador(AnonymousUser())

        conectado, codigo = await comunicador.connect()

        self.assertFalse(conectado)
        self.assertEqual(codigo, 4401)

    async def test_recusa_execucao_inexistente(self):
        """Uma execução que não existe é recusada com o código 4404.

        English:
            A nonexistent execution is refused with code 4404.
        """
        comunicador = self._comunicador(self.usuario, pk=99999)

        conectado, codigo = await comunicador.connect()

        self.assertFalse(conectado)
        self.assertEqual(codigo, 4404)

    async def test_repassa_linhas_e_fim(self):
        """Linhas e fim publicados no grupo chegam ao navegador.

        English:
            Lines and end published to the group reach the browser.
        """
        comunicador = self._comunicador(self.usuario)
        conectado, _ = await comunicador.connect()
        self.assertTrue(conectado)

        camada = get_channel_layer()
        grupo = f"execucao_{self.execucao.pk}"
        await camada.group_send(
            grupo,
            {"type": "log.linhas", "linhas": [{"numero": 1, "texto": "oi"}]},
        )
        await camada.group_send(
            grupo, {"type": "log.fim", "status": "sucesso"}
        )

        self.assertEqual(
            await comunicador.receive_json_from(),
            {"tipo": "linhas", "linhas": [{"numero": 1, "texto": "oi"}]},
        )
        self.assertEqual(
            await comunicador.receive_json_from(),
            {"tipo": "fim", "status": "sucesso"},
        )
        await comunicador.disconnect()

    async def test_manda_o_log_do_banco_ao_conectar(self):
        """Ao conectar, chegam as linhas já gravadas, numeradas.

        English:
            On connect, the lines already saved arrive, numbered.
        """
        self.execucao.log = "linha 9\nlinha 10"
        self.execucao.total_linhas = 10
        await self.execucao.asave()
        comunicador = self._comunicador(self.usuario)

        await comunicador.connect()

        self.assertEqual(
            await comunicador.receive_json_from(),
            {
                "tipo": "linhas",
                "linhas": [
                    {"numero": 9, "texto": "linha 9"},
                    {"numero": 10, "texto": "linha 10"},
                ],
            },
        )
        await comunicador.disconnect()

    async def test_execucao_ja_finalizada_avisa_na_hora(self):
        """Se a execução já terminou, o fim chega logo ao conectar.

        English:
            If the execution already ended, the end arrives right on
            connect.
        """
        self.execucao.status = Execucao.Status.FALHA
        await self.execucao.asave()
        comunicador = self._comunicador(self.usuario)

        await comunicador.connect()

        self.assertEqual(
            await comunicador.receive_json_from(),
            {"tipo": "fim", "status": "falha"},
        )
        await comunicador.disconnect()


class PublicacaoTest(TestCase):
    """Testes das funções que publicam no grupo da execução.

    English:
        Tests for the functions that publish to the execution's group.
    """

    def test_publica_no_grupo_da_execucao(self):
        """As linhas e o fim chegam ao grupo ``execucao_<id>``.

        English:
            Lines and end reach the ``execucao_<id>`` group.
        """
        camada = get_channel_layer()
        canal = async_to_sync(camada.new_channel)()
        async_to_sync(camada.group_add)("execucao_7", canal)

        self.assertTrue(publicar_linhas(7, [{"numero": 1, "texto": "a"}]))
        self.assertTrue(publicar_fim(7, "sucesso"))

        self.assertEqual(
            async_to_sync(camada.receive)(canal)["type"], "log.linhas"
        )
        self.assertEqual(
            async_to_sync(camada.receive)(canal),
            {"type": "log.fim", "status": "sucesso"},
        )

    def test_falha_do_canal_nao_interrompe(self):
        """Se o canal falha, a publicação devolve False sem levantar erro.

        English:
            If the channel fails, publishing returns False without
            raising.
        """
        with mock.patch(
            "executions.ao_vivo.get_channel_layer"
        ) as obter_camada:
            obter_camada.return_value.group_send.side_effect = OSError(
                "Redis fora"
            )
            with self.assertLogs("executions.ao_vivo", "WARNING"):
                resultado = publicar_fim(7, "falha")

        self.assertFalse(resultado)
