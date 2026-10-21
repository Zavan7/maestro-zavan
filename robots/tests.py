"""Testes do app de robôs: model, views e serviço de disparo.

English:
    Tests for the robots app: model, views and trigger service.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import ProtectedError
from django.test import Client, TestCase

from executions.models import Execucao
from robots.models import Robo
from robots.services import DisparoRecusado, disparar_execucao
from robots.tasks import executar_robo

User = get_user_model()


class RoboModelTest(TestCase):
    """Testes do model Robo.

    English:
        Tests for the Robo model.
    """

    def setUp(self):
        """Cria o usuário que será responsável pelos robôs.

        English:
            Creates the user who will own the robots.
        """
        self.usuario = User.objects.create_user(
            username="analista_rpa",
            password="senha-de-teste-123",
        )

    def test_criacao_robo_com_campos_esperados(self):
        """O robô é criado com nome e responsável.

        English:
            The robot is created with its name and owner.
        """
        robo = Robo.objects.create(
            nome="coleta-notas-fiscais",
            descricao="Coleta notas fiscais do portal X",
            caminho_script="/scripts/coleta_notas.py",
            responsavel=self.usuario,
        )

        self.assertEqual(robo.nome, "coleta-notas-fiscais")
        self.assertEqual(robo.responsavel, self.usuario)

    def test_status_padrao_e_ativo(self):
        """Um robô novo começa ativo.

        English:
            A new robot starts as active.
        """
        robo = Robo.objects.create(
            nome="robo-sem-status-explicito",
            caminho_script="/scripts/x.py",
            responsavel=self.usuario,
        )

        self.assertEqual(robo.status, Robo.Status.ATIVO)

    def test_get_status_display_retorna_texto_legivel(self):
        """get_status_display mostra o rótulo com acento, não o valor do banco.

        English:
            get_status_display shows the accented label, not the stored value.
        """
        robo = Robo.objects.create(
            nome="robo-manutencao",
            caminho_script="/scripts/y.py",
            responsavel=self.usuario,
            status=Robo.Status.MANUTENCAO,
        )

        self.assertEqual(robo.get_status_display(), "Manutenção")

    def test_str_retorna_nome_do_robo(self):
        """O __str__ retorna o nome do robô.

        English:
            __str__ returns the robot name.
        """
        robo = Robo.objects.create(
            nome="robo-com-nome-legivel",
            caminho_script="/scripts/z.py",
            responsavel=self.usuario,
        )

        self.assertEqual(str(robo), "robo-com-nome-legivel")

    def test_nao_permite_excluir_usuario_com_robos_associados(self):
        """Usuário responsável por robôs não pode ser excluído.

        Garante o on_delete=PROTECT em responsavel.

        English:
            A user who owns robots cannot be deleted.

            Guarantees on_delete=PROTECT on responsavel.
        """
        Robo.objects.create(
            nome="robo-protegido",
            caminho_script="/scripts/protegido.py",
            responsavel=self.usuario,
        )

        with self.assertRaises(ProtectedError):
            self.usuario.delete()


class RobotViewsTest(TestCase):
    """Testes das views de robôs.

    English:
        Tests for the robot views.
    """

    def setUp(self):
        """Cria um usuário com todas as permissões de robôs e um robô.

        English:
            Creates a user with every robot permission, and a robot.
        """
        self.client = Client()
        self.usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.usuario.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="robots")
        )
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="/scripts/teste.py",
            responsavel=self.usuario,
        )

    def test_robot_list_redireciona_se_deslogado(self):
        """Quem não está logado é redirecionado (302) para o login.

        English:
            Anyone not logged in is redirected (302) to the login page.
        """
        response = self.client.get("/robots/")
        self.assertEqual(response.status_code, 302)

    def test_robot_list_retorna_200_logado(self):
        """Logado, a lista abre e mostra o robô.

        English:
            When logged in, the list opens and shows the robot.
        """
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/robots/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "robo-teste")

    def test_robot_edit_salva_alteracoes(self):
        """Editar via POST grava os novos dados no banco.

        English:
            Editing via POST saves the new data to the database.
        """
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
        """Robô com execução não é excluído e o usuário vê o motivo.

        O ProtectedError vira mensagem em vez de erro 500.

        English:
            A robot with an execution is not deleted and the user sees why.

            The ProtectedError becomes a message instead of a 500 error.
        """
        Execucao.objects.create(robo=self.robo)
        self.client.login(username="analista", password="senha123")
        response = self.client.post(
            f"/robots/{self.robo.pk}/excluir/", follow=True
        )
        self.assertTrue(Robo.objects.filter(pk=self.robo.pk).exists())
        self.assertContains(response, "Não é possível excluir")

    def test_robot_exclusion_funciona_sem_execucao(self):
        """Robô sem execuções é excluído normalmente.

        English:
            A robot without executions is deleted normally.
        """
        self.client.login(username="analista", password="senha123")
        self.client.post(f"/robots/{self.robo.pk}/excluir/")
        self.assertFalse(Robo.objects.filter(pk=self.robo.pk).exists())

    def test_robot_start_recusa_robo_em_manutencao(self):
        """Robô em manutenção não é iniciado.

        English:
            A robot under maintenance is not started.
        """
        self.robo.status = Robo.Status.MANUTENCAO
        self.robo.save()

        self.client.login(username="analista", password="senha123")
        self.client.post(f"/robots/{self.robo.pk}/iniciar/")

        self.assertFalse(
            self.robo.execucoes.filter(
                status=Execucao.Status.RODANDO
            ).exists()
        )

    def test_robot_start_sem_permissao_recebe_403(self):
        """Sem a permissão executar_robo, iniciar responde 403.

        Confirma que a proteção está na view, e não só no botão escondido.

        English:
            Without the executar_robo permission, starting answers 403.

            Confirms the protection is in the view, not just a hidden button.
        """
        User.objects.create_user(username="visitante", password="senha123")
        self.client.login(username="visitante", password="senha123")

        response = self.client.post(f"/robots/{self.robo.pk}/iniciar/")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.robo.execucoes.exists())


class DisparoTest(TestCase):
    """Testes do serviço disparar_execucao.

    English:
        Tests for the disparar_execucao service.
    """

    def setUp(self):
        """Cria um usuário e um robô ativo.

        English:
            Creates a user and an active robot.
        """
        self.usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="teste.py",
            responsavel=self.usuario,
        )

    def test_cria_execucao_pendente_com_quem_disparou(self):
        """O disparo manual cria uma execução pendente com quem disparou.

        English:
            A manual trigger creates a pending execution with who triggered it.
        """
        execucao = disparar_execucao(self.robo, disparado_por=self.usuario)

        self.assertEqual(execucao.status, Execucao.Status.PENDENTE)
        self.assertEqual(execucao.origem, Execucao.Origem.MANUAL)
        self.assertEqual(execucao.disparado_por, self.usuario)

    def test_recusa_robo_inativo(self):
        """Robô inativo é recusado sem criar nenhuma execução.

        English:
            An inactive robot is refused without creating any execution.
        """
        self.robo.status = Robo.Status.INATIVO
        self.robo.save()

        with self.assertRaises(DisparoRecusado):
            disparar_execucao(self.robo)
        self.assertFalse(self.robo.execucoes.exists())

    def test_recusa_quando_ja_tem_execucao_pendente(self):
        """Recusa se já existe uma execução pendente do robô.

        English:
            Refuses if the robot already has a pending execution.
        """
        Execucao.objects.create(
            robo=self.robo, status=Execucao.Status.PENDENTE
        )

        with self.assertRaises(DisparoRecusado):
            disparar_execucao(self.robo)

    def test_recusa_quando_ja_tem_execucao_rodando(self):
        """Recusa se já existe uma execução rodando do robô.

        English:
            Refuses if the robot already has a running execution.
        """
        Execucao.objects.create(robo=self.robo, status=Execucao.Status.RODANDO)

        with self.assertRaises(DisparoRecusado):
            disparar_execucao(self.robo)

    def test_envia_a_tarefa_so_depois_do_commit(self):
        """A tarefa só é enviada ao Celery depois do commit.

        captureOnCommitCallbacks segura os callbacks do on_commit: dentro do
        bloco a tarefa ainda não foi chamada; ao sair, os callbacks rodam e ela
        é chamada uma vez, com o id certo.

        English:
            The task is only sent to Celery after the commit.

            captureOnCommitCallbacks holds the on_commit callbacks: inside the
            block the task has not been called yet; on exit, the callbacks run
            and it is called once, with the right id.
        """
        with mock.patch("robots.services.executar_robo") as tarefa:
            with self.captureOnCommitCallbacks(execute=True):
                execucao = disparar_execucao(self.robo)
                tarefa.delay.assert_not_called()

        tarefa.delay.assert_called_once_with(execucao.id)


class PararExecucaoTest(TestCase):
    """Testes do botão "parar" e da reivindicação feita pela tarefa.

    English:
        Tests for the "stop" button and the claim made by the task.
    """

    def setUp(self):
        """Cria um operador com executar_robo e um robô, e faz login.

        English:
            Creates an operator with executar_robo and a robot, and logs
            in.
        """
        self.client = Client()
        self.usuario = User.objects.create_user(
            username="operador", password="senha123"
        )
        self.usuario.user_permissions.add(
            Permission.objects.get(codename="executar_robo")
        )
        self.robo = Robo.objects.create(
            nome="coleta-notas",
            caminho_script="robo_exemplo.py",
            responsavel=self.usuario,
        )
        self.url = f"/robots/{self.robo.pk}/parar/"
        self.client.login(username="operador", password="senha123")

    def test_cancela_execucao_pendente(self):
        """Uma execução pendente é cancelada como falha, com o motivo no log.

        English:
            A pending execution is cancelled as a failure, with the reason
            in the log.
        """
        execucao = Execucao.objects.create(robo=self.robo)

        response = self.client.post(self.url, follow=True)

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.FALHA)
        self.assertIsNotNone(execucao.finalizado_em)
        self.assertEqual(
            execucao.log, "Cancelada antes de iniciar por operador."
        )
        self.assertContains(response, "Execução pendente de &#x27;")

    def test_tarefa_nao_roda_execucao_cancelada(self):
        """Se a execução já não está pendente, a tarefa não roda o script.

        English:
            If the execution is no longer pending, the task does not run
            the script.
        """
        execucao = Execucao.objects.create(robo=self.robo)
        self.client.post(self.url)

        with mock.patch("robots.tasks.subprocess.run") as rodar:
            executar_robo(execucao.pk)

        rodar.assert_not_called()
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.FALHA)

    def test_tarefa_reivindica_execucao_pendente(self):
        """Uma execução pendente é reivindicada e o script roda.

        English:
            A pending execution is claimed and the script runs.
        """
        execucao = Execucao.objects.create(robo=self.robo)
        concluido = mock.Mock(returncode=0, stdout="ok\n", stderr="")

        with mock.patch(
            "robots.tasks.subprocess.run", return_value=concluido
        ) as rodar:
            executar_robo(execucao.pk)

        rodar.assert_called_once()
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.SUCESSO)
        self.assertIsNotNone(execucao.iniciado_em)

    def test_marca_execucao_rodando_como_finalizada(self):
        """Uma execução rodando é marcada como finalizada.

        English:
            A running execution is marked as finished.
        """
        execucao = Execucao.objects.create(
            robo=self.robo, status=Execucao.Status.RODANDO
        )

        self.client.post(self.url)

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.SUCESSO)
        self.assertIsNotNone(execucao.finalizado_em)

    def test_sem_execucao_em_andamento_mostra_erro(self):
        """Sem execução em andamento, a tela mostra uma mensagem de erro.

        English:
            With no execution in progress, the page shows an error
            message.
        """
        response = self.client.post(self.url, follow=True)

        self.assertContains(response, "não tem execução em andamento")

    def test_sem_permissao_recebe_403(self):
        """Sem executar_robo, parar responde 403 e nada muda.

        English:
            Without executar_robo, stopping answers 403 and nothing
            changes.
        """
        execucao = Execucao.objects.create(robo=self.robo)
        User.objects.create_user(username="visitante", password="senha123")
        self.client.login(username="visitante", password="senha123")

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.PENDENTE)
