"""Testes do app de robôs: model, views e serviço de disparo.

English:
    Tests for the robots app: model, views and trigger service.
"""

import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock, skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import ProtectedError
from django.test import Client, TestCase, override_settings

from config.models import ConfiguracaoSistema
from executions.models import Execucao
from robots.ambiente import (
    Ferramenta,
    Programas,
    ambiente_limpo,
    detectar,
    nome_do_venv,
    planejar,
    rodar_robo,
)
from robots.conclusao import desfecho
from robots.executor import Motivo, executar
from robots.models import Robo
from robots.services import DisparoRecusado, disparar_execucao
from robots.tasks import LogAoVivo, LogLimitado, executar_robo

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
        self.client.post(
            f"/robots/{self.robo.pk}/editar/",
            {
                "nome": "robo-renomeado",
                "caminho_script": self.robo.caminho_script,
                "descricao": "",
                "status": "ativo",
                "max_tentativas": 0,
            },
        )
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
            self.robo.execucoes.filter(status=Execucao.Status.RODANDO).exists()
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


def rodar_python(codigo, timeout=10, deve_parar=lambda: False):
    """Roda um trecho de Python pelo executor e devolve resultado e linhas.

    English:
        Runs a Python snippet through the executor and returns the result
        and the lines.
    """
    linhas = []
    resultado = executar(
        [sys.executable, "-u", "-c", codigo],
        cwd=Path.cwd(),
        timeout_segundos=timeout,
        deve_parar=deve_parar,
        ao_receber_linha=linhas.append,
        intervalo_verificacao=0.2,
        espera_encerramento=1,
    )
    return resultado, linhas


class ExecutorTest(TestCase):
    """Testes do executor com processos reais, sem banco nem worker.

    English:
        Tests for the executor with real processes, no database or worker.
    """

    def test_entrega_as_linhas_e_o_codigo_de_saida(self):
        """Saída padrão e de erro chegam como linhas, com o código de saída.

        English:
            Standard output and error arrive as lines, with the exit code.
        """
        resultado, linhas = rodar_python(
            "import sys; print('um'); print('dois', file=sys.stderr); "
            "sys.exit(3)"
        )

        self.assertEqual(resultado.motivo, Motivo.CONCLUIDO)
        self.assertEqual(resultado.codigo_saida, 3)
        self.assertEqual(linhas, ["um", "dois"])

    def test_encerra_quando_o_tempo_esgota(self):
        """Um processo que passa do tempo limite é encerrado.

        English:
            A process that goes past the timeout is stopped.
        """
        inicio = time.monotonic()

        resultado, _ = rodar_python("import time; time.sleep(30)", timeout=1)

        self.assertEqual(resultado.motivo, Motivo.TEMPO_ESGOTADO)
        self.assertLess(time.monotonic() - inicio, 5)

    def test_encerra_quando_pedem_para_parar(self):
        """Quando deve_parar responde True, o processo é encerrado.

        English:
            When deve_parar answers True, the process is stopped.
        """
        resultado, linhas = rodar_python(
            "import time\nprint('começou')\ntime.sleep(30)",
            deve_parar=lambda: True,
        )

        self.assertEqual(resultado.motivo, Motivo.PARADO)
        self.assertEqual(linhas, ["começou"])

    def test_forca_o_encerramento_de_quem_ignora_o_pedido(self):
        """Um processo que ignora o SIGTERM é encerrado à força.

        English:
            A process that ignores SIGTERM is killed.
        """
        resultado, _ = rodar_python(
            "import signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('pronto', flush=True); time.sleep(30)",
            deve_parar=lambda: True,
        )

        self.assertEqual(resultado.motivo, Motivo.PARADO)
        self.assertEqual(resultado.codigo_saida, -9)


class LogLimitadoTest(TestCase):
    """Testes do acumulador de log com limite de caracteres.

    English:
        Tests for the log accumulator with a character limit.
    """

    def test_guarda_o_fim_do_log(self):
        """Passado o limite, ficam as linhas mais recentes.

        English:
            Past the limit, the most recent lines are kept.
        """
        log = LogLimitado(limite=10)
        for linha in ["aaaa", "bbbb", "cccc"]:
            log.adicionar(linha)

        self.assertEqual(log.texto(), "bbbb\ncccc")


class RelogioFalso:
    """Relógio controlado pelo teste, no lugar de ``time.monotonic``.

    English:
        Test-controlled clock, in place of ``time.monotonic``.
    """

    def __init__(self):
        """Começa no instante zero.

        English:
            Starts at time zero.
        """
        self.agora = 0.0

    def __call__(self):
        """Devolve o instante atual.

        English:
            Returns the current time.
        """
        return self.agora


class LogAoVivoTest(TestCase):
    """Testes dos lotes do log ao vivo, a cada 0,5s, banco antes da tela.

    English:
        Tests for the live log batches, every 0.5s, database before page.
    """

    def setUp(self):
        """Cria uma execução e o log com relógio falso e publicação espiã.

        English:
            Creates an execution and the log with a fake clock and a spy
            publisher.
        """
        usuario = User.objects.create_user(username="u", password="senha123")
        robo = Robo.objects.create(
            nome="robo", caminho_script="robo.py", responsavel=usuario
        )
        self.execucao = Execucao.objects.create(robo=robo)
        self.relogio = RelogioFalso()
        self.log = LogAoVivo(self.execucao.pk, 10_000, relogio=self.relogio)
        patcher = mock.patch("robots.tasks.publicar_linhas")
        self.publicar = patcher.start()
        self.addCleanup(patcher.stop)

    def test_primeira_linha_sai_na_hora_e_as_seguintes_em_lote(self):
        """A primeira linha sai na hora; as próximas esperam 0,5s juntas.

        English:
            The first line goes out right away; the next ones wait 0.5s
            together.
        """
        self.log.adicionar("um")
        self.log.adicionar("dois")
        self.log.adicionar("três")
        self.assertEqual(self.publicar.call_count, 1)

        self.relogio.agora = 0.5
        self.log.despachar()

        self.assertEqual(self.publicar.call_count, 2)
        self.assertEqual(
            self.publicar.call_args.args[1],
            [{"numero": 2, "texto": "dois"}, {"numero": 3, "texto": "três"}],
        )

    def test_grava_no_banco_antes_de_enviar(self):
        """Quando o lote é enviado, as linhas dele já estão no banco.

        English:
            When the batch is sent, its lines are already in the database.
        """
        no_banco_ao_enviar = []
        self.publicar.side_effect = lambda *_: no_banco_ao_enviar.append(
            Execucao.objects.values_list("log", "total_linhas").get(
                pk=self.execucao.pk
            )
        )

        self.log.adicionar("um")

        self.assertEqual(no_banco_ao_enviar, [("um", 1)])

    def test_encerrar_envia_o_que_sobrou(self):
        """Ao encerrar, as linhas acumuladas saem sem esperar o intervalo.

        English:
            On close, the accumulated lines go out without waiting.
        """
        self.log.adicionar("um")
        self.log.adicionar("dois")

        self.log.encerrar()

        self.assertEqual(
            self.publicar.call_args.args[1], [{"numero": 2, "texto": "dois"}]
        )


@override_settings(ROBOS_SCRIPTS_DIR=tempfile.gettempdir())
class ExecutarRoboTaskTest(TestCase):
    """Testes da tarefa que roda o robô, com scripts reais temporários.

    English:
        Tests for the task that runs the robot, with real temporary
        scripts.
    """

    def setUp(self):
        """Cria a pasta de scripts temporária, um usuário e um robô.

        English:
            Creates the temporary scripts folder, a user and a robot.
        """
        self.pasta = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.addCleanup(self.pasta.cleanup)
        self.usuario = User.objects.create_user(
            username="operador", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script=f"{Path(self.pasta.name).name}/robo.py",
            responsavel=self.usuario,
        )

    def _script(self, codigo):
        """Grava o script do robô com o código informado.

        English:
            Writes the robot's script with the given code.
        """
        Path(self.pasta.name, "robo.py").write_text(codigo)

    def _rodar(self, **campos):
        """Cria uma execução pendente, roda a tarefa e devolve a execução.

        English:
            Creates a pending execution, runs the task and returns the
            execution.
        """
        execucao = Execucao.objects.create(robo=self.robo, **campos)
        executar_robo(execucao.pk)
        execucao.refresh_from_db()
        return execucao

    def test_sucesso_grava_o_log(self):
        """Saída 0 vira sucesso, com o log e as datas preenchidos.

        English:
            Exit 0 becomes success, with the log and dates filled in.
        """
        self._script("print('etapa 1')\nprint('etapa 2')")

        execucao = self._rodar()

        self.assertEqual(execucao.status, Execucao.Status.SUCESSO)
        primeira, *saida = execucao.log.splitlines()
        self.assertTrue(primeira.startswith("[ambiente] sem gerenciador"))
        self.assertEqual(saida, ["etapa 1", "etapa 2"])
        self.assertIsNotNone(execucao.iniciado_em)
        self.assertIsNotNone(execucao.finalizado_em)

    def test_publica_as_linhas_e_o_fim(self):
        """A tarefa manda as linhas numeradas e, depois de gravar, o fim.

        English:
            The task sends the numbered lines and, after saving, the end.
        """
        self._script("print('etapa 1')\nprint('etapa 2')")

        with (
            mock.patch("robots.tasks.publicar_linhas") as linhas,
            mock.patch("robots.conclusao.publicar_fim") as fim,
        ):
            execucao = self._rodar()

        enviadas = [
            linha
            for chamada in linhas.call_args_list
            for linha in chamada.args[1]
        ]
        self.assertTrue(enviadas[0]["texto"].startswith("[ambiente]"))
        self.assertEqual(
            enviadas[1:],
            [
                {"numero": 2, "texto": "etapa 1"},
                {"numero": 3, "texto": "etapa 2"},
            ],
        )
        fim.assert_called_once_with(execucao.pk, Execucao.Status.SUCESSO)
        self.assertEqual(execucao.total_linhas, 3)

    def test_tempo_do_robo_esgotado_vira_falha(self):
        """Passar do tempo do próprio robô vira falha, com o motivo no log.

        English:
            Going past the robot's own timeout becomes a failure, with the
            reason in the log.
        """
        self.robo.timeout_segundos = 1
        self.robo.save()
        self._script("import time\ntime.sleep(30)")

        execucao = self._rodar()

        self.assertEqual(execucao.status, Execucao.Status.FALHA)
        self.assertIn("excedeu o limite de 1s", execucao.log)

    def test_robo_sem_tempo_usa_o_padrao(self):
        """Sem tempo próprio, o robô usa o padrão da configuração.

        English:
            With no timeout of its own, the robot uses the settings default.
        """
        configuracao = ConfiguracaoSistema.atual()
        configuracao.timeout_padrao_segundos = 42
        configuracao.save()
        self._script("print('ok')")

        with mock.patch(
            "robots.tasks.rodar_robo", return_value=(Motivo.CONCLUIDO, 0)
        ) as executar_falso:
            self._rodar()

        self.assertEqual(
            executar_falso.call_args.kwargs["timeout_segundos"], 42
        )

    def test_parada_solicitada_cancela(self):
        """Com a parada pedida, o processo é encerrado e vira cancelada.

        English:
            With a stop requested, the process is stopped and it becomes
            cancelled.
        """
        self._script("import time\nprint('rodando')\ntime.sleep(30)")

        execucao = self._rodar(parada_solicitada=True)

        self.assertEqual(execucao.status, Execucao.Status.CANCELADA)
        self.assertIn("parada pelo usuário", execucao.log)

    def test_respeita_o_limite_do_log(self):
        """O log guardado respeita o limite da configuração.

        English:
            The stored log respects the settings limit.
        """
        configuracao = ConfiguracaoSistema.atual()
        configuracao.limite_log = 1_000
        configuracao.save()
        self._script("for i in range(500):\n    print(f'linha {i:04}')")

        execucao = self._rodar()

        self.assertLessEqual(len(execucao.log), 1_000)
        self.assertTrue(execucao.log.endswith("linha 0499"))

    def test_nao_roda_execucao_que_nao_esta_pendente(self):
        """Uma execução já cancelada não é executada pela tarefa.

        English:
            An already cancelled execution is not run by the task.
        """
        execucao = Execucao.objects.create(
            robo=self.robo, status=Execucao.Status.CANCELADA
        )

        with mock.patch("robots.tasks.rodar_robo") as executar_falso:
            executar_robo(execucao.pk)

        executar_falso.assert_not_called()

    def test_falha_dispara_nova_tentativa(self):
        """Com tentativas sobrando, a falha cria a próxima tentativa.

        English:
            With attempts left, a failure creates the next attempt.
        """
        self.robo.max_tentativas = 1
        self.robo.save()
        self._script("import sys\nsys.exit(1)")

        with self.captureOnCommitCallbacks(execute=False) as enviadas:
            primeira = self._rodar(disparado_por=self.usuario)

        segunda = Execucao.objects.exclude(pk=primeira.pk).get()
        self.assertEqual(primeira.status, Execucao.Status.FALHA)
        self.assertEqual(segunda.tentativa, 2)
        self.assertEqual(segunda.status, Execucao.Status.PENDENTE)
        self.assertEqual(segunda.disparado_por, self.usuario)
        self.assertEqual(len(enviadas), 1)

    def test_ultima_tentativa_nao_repete(self):
        """Esgotadas as tentativas, a falha não cria outra execução.

        English:
            Once the attempts run out, a failure creates no other
            execution.
        """
        self.robo.max_tentativas = 1
        self.robo.save()
        self._script("import sys\nsys.exit(1)")

        self._rodar(tentativa=2)

        self.assertEqual(Execucao.objects.count(), 1)

    def test_erro_de_configuracao_nao_repete(self):
        """Script inexistente vira falha, sem nova tentativa.

        English:
            A missing script becomes a failure, with no new attempt.
        """
        self.robo.max_tentativas = 3
        self.robo.caminho_script = "nao_existe.py"
        self.robo.save()

        execucao = self._rodar()

        self.assertEqual(execucao.status, Execucao.Status.FALHA)
        self.assertIn("Script não encontrado", execucao.log)
        self.assertEqual(Execucao.objects.count(), 1)

    def test_cancelada_nao_repete(self):
        """Uma execução parada pelo usuário não ganha nova tentativa.

        English:
            An execution stopped by the user gets no new attempt.
        """
        self.robo.max_tentativas = 3
        self.robo.save()
        self._script("import time\ntime.sleep(30)")

        self._rodar(parada_solicitada=True)

        self.assertEqual(Execucao.objects.count(), 1)


class PararExecucaoTest(TestCase):
    """Testes do botão "parar".

    English:
        Tests for the "stop" button.
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
        """Uma execução pendente é cancelada na hora, com o motivo no log.

        English:
            A pending execution is cancelled right away, with the reason in
            the log.
        """
        execucao = Execucao.objects.create(robo=self.robo)

        response = self.client.post(self.url, follow=True)

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, Execucao.Status.CANCELADA)
        self.assertIsNotNone(execucao.finalizado_em)
        self.assertEqual(
            execucao.log, "Cancelada antes de iniciar por operador."
        )
        self.assertContains(response, "Execução pendente de &#x27;")

    def test_cancelar_pendente_avisa_a_tela(self):
        """Cancelar uma pendente avisa a tela, que recarrega.

        English:
            Cancelling a pending one notifies the page, which reloads.
        """
        execucao = Execucao.objects.create(robo=self.robo)

        with mock.patch("robots.views.publicar_fim") as fim:
            self.client.post(self.url)

        fim.assert_called_once_with(execucao.pk, Execucao.Status.CANCELADA)

    def test_execucao_rodando_recebe_o_pedido_de_parada(self):
        """Uma execução rodando só recebe o pedido; o status fica com a tarefa.

        English:
            A running execution only gets the request; the status is left
            to the task.
        """
        execucao = Execucao.objects.create(
            robo=self.robo, status=Execucao.Status.RODANDO
        )

        response = self.client.post(self.url, follow=True)

        execucao.refresh_from_db()
        self.assertTrue(execucao.parada_solicitada)
        self.assertEqual(execucao.status, Execucao.Status.RODANDO)
        self.assertContains(response, "solicitada")

    def test_lista_mostra_parando(self):
        """Com a parada pedida, a lista de robôs mostra "parando".

        English:
            With a stop requested, the robot list shows "parando".
        """
        Execucao.objects.create(
            robo=self.robo,
            status=Execucao.Status.RODANDO,
            parada_solicitada=True,
        )

        response = self.client.get("/robots/")

        self.assertContains(response, "parando")

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


class AmbienteDoRoboTest(TestCase):
    """Testes da detecção do gerenciador de dependências e do preparo.

    English:
        Tests for dependency manager detection and preparation.
    """

    def setUp(self):
        """Cria uma pasta aprovada temporária com uma pasta de robô.

        English:
            Creates a temporary approved folder with a robot folder.
        """
        temporaria = tempfile.TemporaryDirectory()
        self.addCleanup(temporaria.cleanup)
        self.raiz = Path(temporaria.name)
        self.pasta = self.raiz / "coleta"
        self.pasta.mkdir()
        self.script = self.pasta / "main.py"
        self.script.write_text("import sys\nprint(sys.prefix)\n")

    def _arquivos(self, **conteudos):
        """Grava arquivos na pasta do robô (``Pipfile_lock`` vira ``.lock``).

        English:
            Writes files in the robot's folder (``Pipfile_lock`` becomes
            ``.lock``).
        """
        for nome, conteudo in conteudos.items():
            nome = nome.replace("_lock", ".lock").replace("_txt", ".txt")
            nome = nome.replace("_toml", ".toml")
            (self.pasta / nome).write_text(conteudo)

    def _rodar(self, **opcoes):
        """Roda o robô pelo ``rodar_robo`` e devolve o resultado e o log.

        English:
            Runs the robot through ``rodar_robo`` and returns the result
            and the log.
        """
        linhas = []
        opcoes.setdefault("programas", Programas())
        resultado = rodar_robo(
            self.script,
            pasta_robos=self.raiz,
            timeout_segundos=30,
            deve_parar=lambda: False,
            ao_receber_linha=linhas.append,
            **opcoes,
        )
        return resultado, linhas

    def test_detecta_cada_ferramenta_pelos_arquivos(self):
        """Cada arquivo identifica a ferramenta, com os locks na frente.

        English:
            Each file identifies the tool, with the locks first.
        """
        poetry = '[tool.poetry]\nname = "x"\n'
        casos = [
            ({"uv_lock": "", "pyproject_toml": poetry}, Ferramenta.UV),
            ({"poetry_lock": ""}, Ferramenta.POETRY),
            ({"pdm_lock": ""}, Ferramenta.PDM),
            ({"Pipfile": ""}, Ferramenta.PIPENV),
            ({"pyproject_toml": poetry}, Ferramenta.POETRY),
            ({"pyproject_toml": "[tool.pdm]\n"}, Ferramenta.PDM),
            ({"pyproject_toml": "[project]\nname = 'x'\n"}, Ferramenta.UV),
            ({"pyproject_toml": "isto não é toml ["}, Ferramenta.UV),
            ({"requirements_txt": "six\n"}, Ferramenta.PIP),
            ({}, Ferramenta.SISTEMA),
        ]
        for arquivos, esperada in casos:
            with self.subTest(arquivos=list(arquivos)):
                for arquivo in self.pasta.iterdir():
                    if arquivo != self.script:
                        arquivo.unlink()
                self._arquivos(**arquivos)
                self.assertEqual(detectar(self.pasta)[0], esperada)

    def test_nao_sobe_para_as_pastas_de_cima(self):
        """Um pyproject.toml acima da pasta do robô não conta.

        English:
            A pyproject.toml above the robot's folder does not count.
        """
        (self.raiz / "pyproject.toml").write_text("[project]\n")

        self.assertEqual(detectar(self.pasta)[0], Ferramenta.SISTEMA)

    def test_nome_do_venv_vem_do_caminho_do_robo(self):
        """O nome do venv junta as pastas com ``__``; a raiz vira ``_raiz``.

        English:
            The venv name joins the folders with ``__``; the root becomes
            ``_raiz``.
        """
        aninhada = self.pasta / "notas"
        aninhada.mkdir()

        self.assertEqual(nome_do_venv(self.raiz, aninhada), "coleta__notas")
        self.assertEqual(nome_do_venv(self.raiz, self.raiz), "_raiz")

    def test_ambiente_limpo_nao_vaza_o_venv_nem_o_token(self):
        """Sai o venv ativo (variáveis e PATH) e o token; entra o -u.

        English:
            The active venv (variables and PATH) and the token go out;
            unbuffered output comes in.
        """
        limpo = ambiente_limpo(
            {
                "PATH": "/opt/venv/bin:/usr/bin",
                "VIRTUAL_ENV": "/opt/venv",
                "UV_PROJECT_ENVIRONMENT": "/opt/venv",
                "MAESTRO_TOKEN": "mae_x",
                "HOME": "/home/robo",
            }
        )

        self.assertEqual(
            limpo,
            {
                "PATH": "/usr/bin",
                "HOME": "/home/robo",
                "PYTHONUNBUFFERED": "1",
            },
        )

    def test_plano_guarda_cada_ambiente_fora_da_pasta(self):
        """Com pasta de venvs, cada ferramenta recebe a sua variável.

        English:
            With a venvs folder, each tool gets its own variable.
        """
        venvs = self.raiz / "venvs"
        casos = [
            ({"uv_lock": ""}, "UV_PROJECT_ENVIRONMENT"),
            ({"poetry_lock": ""}, "POETRY_VIRTUALENVS_PATH"),
            ({"Pipfile_lock": "{}"}, "WORKON_HOME"),
        ]
        for arquivos, variavel in casos:
            with self.subTest(variavel=variavel):
                for arquivo in self.pasta.iterdir():
                    if arquivo != self.script:
                        arquivo.unlink()
                self._arquivos(**arquivos)
                plano = planejar(self.script, Programas(), self.raiz, venvs)
                self.assertEqual(plano.env[variavel], str(venvs / "coleta"))

    def test_pipenv_sincroniza_com_lock_e_instala_sem(self):
        """Com Pipfile.lock, ``pipenv sync``; só com Pipfile, ``install``.

        English:
            With Pipfile.lock, ``pipenv sync``; with only a Pipfile,
            ``install``.
        """
        self._arquivos(Pipfile="")
        self.assertEqual(
            planejar(self.script, Programas(), self.raiz).preparo,
            [["pipenv", "install"]],
        )
        self._arquivos(Pipfile_lock="{}")
        self.assertEqual(
            planejar(self.script, Programas(), self.raiz).preparo,
            [["pipenv", "sync"]],
        )

    def test_ferramenta_ausente_e_ambiente_invalido(self):
        """Sem a ferramenta instalada, nada roda e o motivo vai para o log.

        English:
            Without the tool installed, nothing runs and the reason goes to
            the log.
        """
        self._arquivos(poetry_lock="")

        with mock.patch("robots.ambiente.executar") as executar_falso:
            (motivo, codigo), linhas = self._rodar(
                programas=Programas(poetry="poetry-que-nao-existe")
            )

        executar_falso.assert_not_called()
        self.assertEqual((motivo, codigo), (Motivo.AMBIENTE_INVALIDO, None))
        self.assertIn("não está instalado nesta máquina", linhas[-1])

    def test_requirements_roda_no_proprio_venv(self):
        """Com requirements.txt, cria o venv, instala e roda dentro dele.

        English:
            With requirements.txt, it creates the venv, installs and runs
            inside it.
        """
        self._arquivos(requirements_txt="# sem dependências\n")
        venvs = self.raiz / "venvs"

        (motivo, codigo), linhas = self._rodar(pasta_venvs=venvs)

        self.assertEqual((motivo, codigo), (Motivo.CONCLUIDO, 0))
        self.assertEqual(linhas[-1], str(venvs / "coleta"))

    def test_preparo_que_falha_e_preparo_falhou(self):
        """Um requirements.txt inválido faz o preparo falhar, sem rodar.

        English:
            An invalid requirements.txt makes preparation fail, without
            running.
        """
        self._arquivos(requirements_txt="=== isto não é um requisito\n")

        (motivo, _), linhas = self._rodar(pasta_venvs=self.raiz / "venvs")

        self.assertEqual(motivo, Motivo.PREPARO_FALHOU)
        self.assertTrue(linhas[-1].startswith("[ambiente] preparo falhou"))

    def test_parada_no_preparo_e_parado(self):
        """Uma parada pedida durante o preparo encerra como parado.

        English:
            A stop requested during preparation ends as stopped.
        """
        self._arquivos(uv_lock="")
        parado = mock.Mock(motivo=Motivo.PARADO, codigo_saida=-15)

        with (
            mock.patch("robots.ambiente.shutil.which", return_value="/uv"),
            mock.patch(
                "robots.ambiente.executar", return_value=parado
            ) as executar_falso,
        ):
            (motivo, _), _ = self._rodar()

        self.assertEqual(motivo, Motivo.PARADO)
        executar_falso.assert_called_once()

    @skipUnless(shutil.which("uv"), "uv não está instalado")
    def test_projeto_uv_roda_no_ambiente_dele(self):
        """Um projeto uv sem dependências sincroniza e roda no venv dele.

        English:
            A uv project with no dependencies syncs and runs in its venv.
        """
        self._arquivos(
            pyproject_toml='[project]\nname = "coleta"\nversion = "0.1.0"\n'
        )
        venvs = self.raiz / "venvs"

        (motivo, codigo), linhas = self._rodar(pasta_venvs=venvs)

        self.assertEqual((motivo, codigo), (Motivo.CONCLUIDO, 0))
        self.assertEqual(linhas[-1], str(venvs / "coleta"))

    def test_desfecho_dos_motivos_de_ambiente(self):
        """Ambiente inválido não repete; preparo que falhou repete.

        English:
            An invalid environment does not repeat; a failed preparation
            does.
        """
        invalido = desfecho(Motivo.AMBIENTE_INVALIDO, None, 300)
        preparo = desfecho(Motivo.PREPARO_FALHOU, 1, 300)

        self.assertEqual(invalido.status, Execucao.Status.FALHA)
        self.assertFalse(invalido.pode_repetir)
        self.assertEqual(preparo.status, Execucao.Status.FALHA)
        self.assertTrue(preparo.pode_repetir)
