"""Testes do app de agentes: model, protocolo, consumer, disparo e telas.

English:
    Tests for the agents app: model, protocol, consumer, trigger and
    pages.
"""

from datetime import timedelta
from unittest import mock

from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import Group, User
from django.forms import ModelChoiceField
from django.test import TestCase
from django.urls import path
from django.utils import timezone

from agents.consumers import AgenteConsumer
from agents.models import Agente, hash_do_token
from agents.protocolo import (
    MensagemInvalida,
    autenticar,
    confirmar_inicio,
    receber_fim,
    receber_linhas,
)
from config.models import RegistroAcesso
from executions.models import Execucao
from robots.forms import RoboForm
from robots.models import Robo
from robots.services import DisparoRecusado, disparar_execucao

# Os stubs tipam o path() só para views HTTP; o Channels o usa com apps
# ASGI.
ROTAS = [path("ws/agente/", AgenteConsumer.as_asgi())]  # type: ignore[arg-type]


class BaseAgente(TestCase):
    """Base com usuário, agente online e um robô que roda nele.

    English:
        Base with a user, an online agent and a robot that runs on it.
    """

    def setUp(self):
        """Cria usuário, agente online (com token conhecido) e robô.

        English:
            Creates a user, an online agent (with a known token) and a
            robot.
        """
        self.usuario = User.objects.create_user(
            username="admin_rpa", password="senha123"
        )
        self.agente = Agente(nome="servidor-01", ultimo_sinal=timezone.now())
        self.token = self.agente.novo_token()
        self.agente.save()
        self.robo = Robo.objects.create(
            nome="coleta",
            caminho_script="coleta/main.py",
            responsavel=self.usuario,
            agente=self.agente,
        )

    def _execucao(self, **campos):
        """Cria uma execução do robô do agente.

        English:
            Creates an execution of the agent's robot.
        """
        return Execucao.objects.create(robo=self.robo, **campos)


class AgenteModelTest(BaseAgente):
    """Testes do token e do estado online do agente.

    English:
        Tests for the agent's token and online state.
    """

    def test_guarda_so_o_hash_do_token(self):
        """O banco guarda o hash; o token em texto não aparece em lugar algum.

        English:
            The database keeps the hash; the plain token shows up nowhere.
        """
        self.agente.refresh_from_db()

        self.assertTrue(self.token.startswith("mae_"))
        self.assertEqual(self.agente.token_hash, hash_do_token(self.token))
        self.assertNotIn(self.token, self.agente.token_hash)

    def test_online_depende_do_ultimo_sinal(self):
        """Online com sinal recente; offline com sinal velho ou desativado.

        English:
            Online with a recent signal; offline with an old signal or
            deactivated.
        """
        agora = timezone.now()
        self.assertTrue(self.agente.online(agora))
        self.assertFalse(self.agente.online(agora + timedelta(minutes=5)))
        self.agente.ativo = False
        self.assertFalse(self.agente.online(agora))


class ProtocoloTest(BaseAgente):
    """Testes das regras de cada mensagem do agente, sem WebSocket.

    English:
        Tests for the rules of each agent message, without WebSocket.
    """

    def test_autentica_so_token_valido_de_agente_ativo(self):
        """Token certo autentica; errado ou de agente desativado, não.

        English:
            The right token authenticates; a wrong one or a deactivated
            agent's does not.
        """
        self.assertEqual(autenticar(self.token), self.agente)
        self.assertIsNone(autenticar("mae_errado"))
        self.agente.ativo = False
        self.agente.save()
        self.assertIsNone(autenticar(self.token))

    def test_confirmar_inicio_reivindica_so_pendente_do_agente(self):
        """Só uma execução pendente deste agente vira rodando.

        English:
            Only a pending execution of this agent becomes running.
        """
        execucao = self._execucao()
        outro = Agente.objects.create(nome="outro", token_hash="x" * 64)

        self.assertFalse(confirmar_inicio(outro.pk, execucao.pk))
        self.assertTrue(confirmar_inicio(self.agente.pk, execucao.pk))
        self.assertFalse(confirmar_inicio(self.agente.pk, execucao.pk))
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.RODANDO)

    def test_linhas_entram_no_log_e_vao_numeradas_para_a_tela(self):
        """As linhas são gravadas e publicadas com a numeração contínua.

        English:
            Lines are saved and published with continuous numbering.
        """
        execucao = self._execucao(
            status=Execucao.Status.RODANDO, log="um", total_linhas=1
        )

        with mock.patch("agents.protocolo.publicar_linhas") as publicar:
            receber_linhas(
                self.agente.pk,
                {"execucao_id": execucao.pk, "linhas": ["dois", "três"]},
            )

        execucao.refresh_from_db()
        self.assertEqual(execucao.log, "um\ndois\ntrês")
        self.assertEqual(execucao.total_linhas, 3)
        publicar.assert_called_once_with(
            execucao.pk,
            [{"numero": 2, "texto": "dois"}, {"numero": 3, "texto": "três"}],
        )

    def test_linhas_invalidas_sao_recusadas(self):
        """Linhas fora do formato, de outro agente ou fora de hora: recusa.

        English:
            Malformed lines, another agent's, or at the wrong time: refused.
        """
        rodando = self._execucao(status=Execucao.Status.RODANDO)
        pendente = Execucao.objects.create(
            robo=Robo.objects.create(
                nome="outro", caminho_script="x.py", responsavel=self.usuario
            ),
            status=Execucao.Status.RODANDO,
        )
        invalidas = [
            {"execucao_id": rodando.pk, "linhas": "texto"},
            {"execucao_id": rodando.pk, "linhas": [1, 2]},
            {"execucao_id": "1", "linhas": []},
            {"execucao_id": rodando.pk, "linhas": ["x"] * 1_001},
            {"execucao_id": pendente.pk, "linhas": ["de outro agente"]},
        ]
        for mensagem in invalidas:
            with self.subTest(mensagem=str(mensagem)[:60]):
                with self.assertRaises(MensagemInvalida):
                    receber_linhas(self.agente.pk, mensagem)

    def test_fim_usa_as_regras_do_worker_e_tenta_de_novo(self):
        """Falha com tentativas sobrando cria a próxima e manda iniciar.

        English:
            A failure with attempts left creates the next one and sends
            the start command.
        """
        self.robo.max_tentativas = 1
        self.robo.save()
        execucao = self._execucao(status=Execucao.Status.RODANDO)

        with (
            mock.patch("robots.services.mandar_iniciar") as iniciar,
            self.captureOnCommitCallbacks(execute=True),
        ):
            receber_fim(
                self.agente.pk,
                {
                    "execucao_id": execucao.pk,
                    "motivo": "concluido",
                    "codigo_saida": 1,
                },
            )

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.FALHA)
        segunda = Execucao.objects.exclude(pk=execucao.pk).get()
        self.assertEqual(segunda.tentativa, 2)
        iniciar.assert_called_once_with(
            self.agente.pk, segunda.pk, "coleta/main.py", 300
        )

    def test_fim_por_tempo_esgotado_registra_o_aviso(self):
        """Tempo esgotado vira falha com o aviso no fim do log.

        English:
            A timeout becomes a failure with the warning at the end of the
            log.
        """
        execucao = self._execucao(status=Execucao.Status.RODANDO, log="a")

        receber_fim(
            self.agente.pk,
            {"execucao_id": execucao.pk, "motivo": "tempo_esgotado"},
        )

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.FALHA)
        self.assertEqual(execucao.log, "a\nExecução excedeu o limite de 300s.")
        self.assertEqual(execucao.total_linhas, 1)

    def test_fim_de_execucao_ja_encerrada_e_ignorado(self):
        """Um fim que chega depois do cancelamento não muda nada.

        English:
            An end that arrives after the cancellation changes nothing.
        """
        execucao = self._execucao(status=Execucao.Status.CANCELADA)

        receber_fim(
            self.agente.pk,
            {
                "execucao_id": execucao.pk,
                "motivo": "concluido",
                "codigo_saida": 0,
            },
        )

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.CANCELADA)

    def test_fim_com_motivo_desconhecido_e_recusado(self):
        """Um motivo fora do protocolo é recusado.

        English:
            A reason outside the protocol is refused.
        """
        execucao = self._execucao(status=Execucao.Status.RODANDO)

        with self.assertRaises(MensagemInvalida):
            receber_fim(
                self.agente.pk,
                {"execucao_id": execucao.pk, "motivo": "explodiu"},
            )


class AgenteConsumerTest(BaseAgente):
    """Testes do WebSocket do agente, de ponta a ponta no protocolo.

    English:
        Tests for the agent WebSocket, end to end on the protocol.
    """

    def _comunicador(self, token=None):
        """Monta o comunicador com o token no cabeçalho, se houver.

        English:
            Builds the communicator with the token in the header, if any.
        """
        cabecalhos = (
            [(b"authorization", f"Bearer {token}".encode())] if token else []
        )
        return WebsocketCommunicator(
            URLRouter(ROTAS),  # type: ignore[arg-type]
            "/ws/agente/",
            headers=cabecalhos,
        )

    async def test_recusa_sem_token_ou_com_token_errado(self):
        """Sem token ou com token errado, a conexão é recusada (4401).

        English:
            Without a token or with a wrong one, the connection is refused
            (4401).
        """
        for token in (None, "mae_errado"):
            with self.subTest(token=token):
                conectado, codigo = await self._comunicador(token).connect()
                self.assertFalse(conectado)
                self.assertEqual(codigo, 4401)

    async def test_conecta_e_registra_o_sinal(self):
        """Com o token certo, conecta e atualiza o último sinal.

        English:
            With the right token, it connects and updates the last signal.
        """
        self.agente.ultimo_sinal = None
        await self.agente.asave()
        comunicador = self._comunicador(self.token)

        conectado, _ = await comunicador.connect()

        self.assertTrue(conectado)
        await self.agente.arefresh_from_db()
        self.assertIsNotNone(self.agente.ultimo_sinal)
        await comunicador.disconnect()

    async def test_repassa_os_comandos_do_maestro(self):
        """Um comando enviado ao grupo chega ao agente como está.

        English:
            A command sent to the group reaches the agent as is.
        """
        comunicador = self._comunicador(self.token)
        await comunicador.connect()

        camada = get_channel_layer()
        assert camada is not None
        await camada.group_send(
            f"agente_{self.agente.pk}",
            {
                "type": "agente.comando",
                "mensagem": {"tipo": "parar", "execucao_id": 7},
            },
        )

        self.assertEqual(
            await comunicador.receive_json_from(),
            {"tipo": "parar", "execucao_id": 7},
        )
        await comunicador.disconnect()

    async def test_nova_conexao_derruba_a_anterior(self):
        """Ao reconectar, a conexão antiga fecha com 4409.

        English:
            On reconnecting, the old connection closes with 4409.
        """
        antiga = self._comunicador(self.token)
        await antiga.connect()

        nova = self._comunicador(self.token)
        await nova.connect()

        self.assertEqual(
            await antiga.receive_output(),
            {
                "type": "websocket.close",
                "code": 4409,
            },
        )
        await nova.disconnect()

    async def test_mensagem_invalida_volta_como_erro(self):
        """Tipo desconhecido volta como erro, e a conexão continua.

        English:
            An unknown type comes back as an error, and the connection
            stays.
        """
        comunicador = self._comunicador(self.token)
        await comunicador.connect()

        await comunicador.send_json_to({"tipo": "dancar"})
        resposta = await comunicador.receive_json_from()
        await comunicador.send_json_to({"tipo": "heartbeat"})

        self.assertEqual(resposta["tipo"], "erro")
        self.assertTrue(await comunicador.receive_nothing())
        await comunicador.disconnect()

    async def test_iniciado_de_execucao_cancelada_recebe_parar(self):
        """Se a execução foi cancelada no caminho, o agente recebe parar.

        English:
            If the execution was cancelled along the way, the agent gets
            stop.
        """
        execucao = await Execucao.objects.acreate(
            robo=self.robo, status=Execucao.Status.CANCELADA
        )
        comunicador = self._comunicador(self.token)
        await comunicador.connect()

        await comunicador.send_json_to(
            {"tipo": "iniciado", "execucao_id": execucao.pk}
        )

        self.assertEqual(
            await comunicador.receive_json_from(),
            {"tipo": "parar", "execucao_id": execucao.pk},
        )
        await comunicador.disconnect()

    async def test_fluxo_completo_iniciado_log_fim(self):
        """iniciado, log e fim levam a execução até sucesso, com o log.

        English:
            iniciado, log and fim take the execution to success, with the
            log.
        """
        execucao = await Execucao.objects.acreate(robo=self.robo)
        comunicador = self._comunicador(self.token)
        await comunicador.connect()

        for mensagem in (
            {"tipo": "iniciado", "execucao_id": execucao.pk},
            {"tipo": "log", "execucao_id": execucao.pk, "linhas": ["ok"]},
            {
                "tipo": "fim",
                "execucao_id": execucao.pk,
                "motivo": "concluido",
                "codigo_saida": 0,
            },
        ):
            await comunicador.send_json_to(mensagem)
        self.assertTrue(await comunicador.receive_nothing(timeout=0.5))

        await execucao.arefresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.SUCESSO)
        self.assertEqual(execucao.log, "ok")
        self.assertIsNotNone(execucao.finalizado_em)
        await comunicador.disconnect()


class DisparoComAgenteTest(BaseAgente):
    """Testes do disparo e da parada de robôs que rodam num agente.

    English:
        Tests for triggering and stopping robots that run on an agent.
    """

    def test_agente_offline_recusa_o_disparo(self):
        """Com o agente offline, o disparo é recusado e nada é criado.

        English:
            With the agent offline, the trigger is refused and nothing is
            created.
        """
        self.agente.ultimo_sinal = timezone.now() - timedelta(minutes=5)
        self.agente.save()

        with self.assertRaisesMessage(DisparoRecusado, "offline"):
            disparar_execucao(self.robo)
        self.assertFalse(Execucao.objects.exists())

    def test_agente_online_recebe_iniciar_e_nao_o_worker(self):
        """Com agente, o comando vai ao agente, e a tarefa não é enviada.

        English:
            With an agent, the command goes to the agent, and the task is
            not sent.
        """
        with (
            mock.patch("robots.services.mandar_iniciar") as iniciar,
            mock.patch("robots.services.executar_robo") as tarefa,
            self.captureOnCommitCallbacks(execute=True),
        ):
            execucao = disparar_execucao(self.robo)

        iniciar.assert_called_once_with(
            self.agente.pk, execucao.pk, "coleta/main.py", 300
        )
        tarefa.delay.assert_not_called()

    def _parar(self):
        """Faz login com permissão de executar e clica em parar.

        English:
            Logs in with run permission and clicks stop.
        """
        self.usuario.groups.add(Group.objects.get(name="Operador"))
        self.client.login(username="admin_rpa", password="senha123")
        return self.client.post(f"/robots/{self.robo.pk}/parar/", follow=True)

    def test_parar_rodando_manda_o_comando_ao_agente(self):
        """Parar com o agente online marca o pedido e manda parar.

        English:
            Stopping with the agent online sets the request and sends
            stop.
        """
        execucao = self._execucao(status=Execucao.Status.RODANDO)

        with mock.patch("robots.views.mandar_parar") as parar:
            self._parar()

        parar.assert_called_once_with(self.agente.pk, execucao.pk)
        execucao.refresh_from_db()
        self.assertTrue(execucao.parada_solicitada)
        self.assertEqual(execucao.status, Execucao.Status.RODANDO)

    def test_parar_com_agente_offline_cancela_na_hora(self):
        """Sem ninguém para receber o pedido, a execução é cancelada.

        English:
            With nobody to receive the request, the execution is
            cancelled.
        """
        self.agente.ultimo_sinal = timezone.now() - timedelta(minutes=5)
        self.agente.save()
        execucao = self._execucao(status=Execucao.Status.RODANDO)

        with mock.patch("robots.views.mandar_parar"):
            response = self._parar()

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.CANCELADA)
        self.assertIn("offline", execucao.log)
        self.assertContains(response, "o agente está offline")


class AgentViewsTest(TestCase):
    """Testes das telas de agentes na aba de configurações.

    English:
        Tests for the agent pages in the settings tab.
    """

    def setUp(self):
        """Cria um administrador do sistema e um operador; login no admin.

        English:
            Creates a system administrator and an operator; logs in as the
            administrator.
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
        self.client.login(username="admin_sistema", password="senha123")

    def test_lista_para_o_administrador_do_sistema(self):
        """O administrador do sistema vê a lista de agentes.

        English:
            The system administrator sees the agent list.
        """
        Agente.objects.create(nome="servidor-01", token_hash="a" * 64)

        response = self.client.get("/configuracoes/agentes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servidor-01")
        self.assertContains(response, "nunca conectou")

    def test_operador_recebe_403_e_deslogado_vai_ao_login(self):
        """Sem a permissão, 403; sem login, redireciona.

        English:
            Without the permission, 403; without login, redirect.
        """
        self.client.login(username="operador", password="senha123")
        self.assertEqual(
            self.client.get("/configuracoes/agentes/").status_code, 403
        )
        self.client.logout()
        self.assertEqual(
            self.client.get("/configuracoes/agentes/").status_code, 302
        )

    def test_criar_mostra_o_token_uma_vez_e_registra(self):
        """Criar mostra o token, guarda só o hash e grava a auditoria.

        English:
            Creating shows the token, stores only the hash and writes the
            audit record.
        """
        response = self.client.post(
            "/configuracoes/agentes/novo/", {"nome": "servidor-01"}
        )

        token = response.context["token"]
        agente = Agente.objects.get(nome="servidor-01")
        self.assertContains(response, token)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(agente.token_hash, hash_do_token(token))
        self.assertEqual(agente.criado_por, self.admin)
        self.assertEqual(
            RegistroAcesso.objects.get().detalhe, "servidor-01: criado"
        )
        self.assertNotContains(
            self.client.get("/configuracoes/agentes/"), token
        )

    def test_nome_repetido_mostra_erro(self):
        """Um nome já usado não cria outro agente.

        English:
            A name already in use does not create another agent.
        """
        Agente.objects.create(nome="servidor-01", token_hash="a" * 64)

        response = self.client.post(
            "/configuracoes/agentes/novo/", {"nome": "servidor-01"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Agente.objects.count(), 1)
        self.assertContains(response, "error-message")

    def test_novo_token_troca_o_hash_e_derruba_a_conexao(self):
        """O token novo invalida o antigo e fecha a conexão aberta.

        English:
            The new token invalidates the old one and closes the open
            connection.
        """
        agente = Agente(nome="servidor-01")
        antigo = agente.novo_token()
        agente.save()

        with (
            mock.patch("agents.services.desconectar") as desconectar,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                f"/configuracoes/agentes/{agente.pk}/token/"
            )

        novo = response.context["token"]
        self.assertNotEqual(novo, antigo)
        self.assertIsNone(autenticar(antigo))
        self.assertEqual(autenticar(novo), agente)
        desconectar.assert_called_once_with(agente.pk)

    def test_desativar_e_reativar(self):
        """Alternar desativa (derrubando a conexão) e depois reativa.

        English:
            Toggling deactivates (dropping the connection) and then
            reactivates.
        """
        agente = Agente.objects.create(nome="servidor-01", token_hash="a" * 64)
        url = f"/configuracoes/agentes/{agente.pk}/alternar/"

        with (
            mock.patch("agents.services.desconectar") as desconectar,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.post(url)
        agente.refresh_from_db()
        self.assertFalse(agente.ativo)
        desconectar.assert_called_once_with(agente.pk)

        self.client.post(url)
        agente.refresh_from_db()
        self.assertTrue(agente.ativo)

    def test_get_nao_altera_nada(self):
        """GET nas ações não cria, não troca token e não desativa.

        English:
            GET on the actions creates nothing, changes no token and
            deactivates nothing.
        """
        agente = Agente.objects.create(nome="servidor-01", token_hash="a" * 64)

        self.client.get("/configuracoes/agentes/novo/", {"nome": "x"})
        self.client.get(f"/configuracoes/agentes/{agente.pk}/token/")
        self.client.get(f"/configuracoes/agentes/{agente.pk}/alternar/")

        agente.refresh_from_db()
        self.assertEqual(agente.token_hash, "a" * 64)
        self.assertTrue(agente.ativo)
        self.assertEqual(Agente.objects.count(), 1)

    def test_formulario_de_robo_so_oferece_agentes_ativos(self):
        """Agente desativado não aparece no formulário de um robô novo.

        English:
            A deactivated agent does not show up in a new robot's form.
        """
        Agente.objects.create(nome="ativo", token_hash="a" * 64)
        Agente.objects.create(
            nome="desativado", token_hash="b" * 64, ativo=False
        )

        campo = RoboForm().fields["agente"]
        assert isinstance(campo, ModelChoiceField)
        assert campo.queryset is not None
        nomes = list(campo.queryset.values_list("nome", flat=True))

        self.assertEqual(nomes, ["ativo"])
