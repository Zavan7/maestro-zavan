"""Testes do app de agendamentos: model, tarefa e views.

English:
    Tests for the schedules app: model, task and views.
"""
from datetime import datetime, time
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from executions.models import Execucao
from robots.models import Robo
from scheduler import tasks
from scheduler.models import DIAS_DA_SEMANA, Agendamento, formatar_proxima

User = get_user_model()

SEGUNDA_7H = timezone.make_aware(datetime(2026, 9, 28, 7, 0))
SEGUNDA_9H = timezone.make_aware(datetime(2026, 9, 28, 9, 0))


def dias(*marcados):
    """Monta os sete campos de dia, marcando só os informados.

    Exemplo: dias("segunda") devolve {"segunda": True, "terca": False, ...}.
    Com ** na chamada, o dicionário vira argumentos nomeados do model.

    English:
        Builds the seven day fields, checking only the given ones.

        Example: dias("segunda") returns {"segunda": True, "terca": False,
        ...}. With ** in the call, the dict becomes keyword arguments for
        the model.
    """
    return {dia: dia in marcados for dia in DIAS_DA_SEMANA}


class AgendamentoModelTest(TestCase):
    """Testes do model Agendamento e de formatar_proxima.

    English:
        Tests for the Agendamento model and formatar_proxima.
    """

    def setUp(self):
        """Cria um usuário e um robô para agendar.

        English:
            Creates a user and a robot to schedule.
        """
        usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-agendado",
            caminho_script="robo_exemplo.py",
            responsavel=usuario,
        )

    def test_recusa_agendamento_sem_nenhum_dia(self):
        """Agendamento sem nenhum dia marcado é inválido.

        English:
            A schedule with no day checked is invalid.
        """
        agendamento = Agendamento(
            robo=self.robo, horario=time(8, 0), **dias()
        )

        with self.assertRaises(ValidationError):
            agendamento.full_clean()

    def test_save_zera_os_segundos(self):
        """O save descarta os segundos do horário.

        English:
            save drops the seconds from the time.
        """
        agendamento = Agendamento.objects.create(
            robo=self.robo, horario=time(8, 0, 30)
        )

        agendamento.refresh_from_db()
        self.assertEqual(agendamento.horario, time(8, 0))

    def test_dias_formatados(self):
        """Os dias marcados viram um resumo legível.

        English:
            The checked days become a readable summary.
        """
        uteis = Agendamento(robo=self.robo, horario=time(8, 0))
        todos = Agendamento(
            robo=self.robo, horario=time(9, 0), **dias(*DIAS_DA_SEMANA)
        )
        alguns = Agendamento(
            robo=self.robo,
            horario=time(10, 0),
            **dias("segunda", "sabado"),
        )

        self.assertEqual(uteis.dias_formatados(), "dias úteis")
        self.assertEqual(todos.dias_formatados(), "todos os dias")
        self.assertEqual(alguns.dias_formatados(), "seg, sáb")

    def test_proxima_ocorrencia_ainda_hoje(self):
        """Se o horário de hoje ainda não passou, a próxima é hoje.

        English:
            If today's time has not passed yet, the next run is today.
        """
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0))

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_7H)

        self.assertEqual(
            proxima, timezone.make_aware(datetime(2026, 9, 28, 8, 0))
        )

    def test_proxima_ocorrencia_quando_o_horario_ja_passou(self):
        """Se o horário de hoje já passou, a próxima é amanhã.

        English:
            If today's time has already passed, the next run is tomorrow.
        """
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0))

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_9H)

        self.assertEqual(
            proxima, timezone.make_aware(datetime(2026, 9, 29, 8, 0))
        )

    def test_proxima_ocorrencia_pula_dias_desmarcados(self):
        """Os dias desmarcados são pulados até o próximo dia marcado.

        English:
            Unchecked days are skipped until the next checked day.
        """
        agendamento = Agendamento(
            robo=self.robo, horario=time(8, 0), **dias("sexta")
        )

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_7H)

        self.assertEqual(
            proxima, timezone.make_aware(datetime(2026, 10, 2, 8, 0))
        )

    def test_proxima_ocorrencia_no_mesmo_dia_da_semana_seguinte(self):
        """Com só hoje marcado e o horário já passado, cai na semana seguinte.

        English:
            With only today checked and the time already passed, it lands on
            next week.
        """
        agendamento = Agendamento(
            robo=self.robo, horario=time(8, 0), **dias("segunda")
        )

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_9H)

        self.assertEqual(
            proxima, timezone.make_aware(datetime(2026, 10, 5, 8, 0))
        )

    def test_formatar_proxima(self):
        """Formata como hoje, amanhã ou dia da semana.

        English:
            Formats as today, tomorrow or weekday.
        """
        hoje = timezone.make_aware(datetime(2026, 9, 28, 8, 0))
        amanha = timezone.make_aware(datetime(2026, 9, 29, 8, 0))
        sexta = timezone.make_aware(datetime(2026, 10, 2, 8, 0))

        self.assertEqual(formatar_proxima(hoje, SEGUNDA_7H), "hoje 08:00")
        self.assertEqual(
            formatar_proxima(amanha, SEGUNDA_7H), "amanhã 08:00"
        )
        self.assertEqual(formatar_proxima(sexta, SEGUNDA_7H), "sex 08:00")


class VerificarAgendamentosTest(TestCase):
    """Testes da tarefa verificar_agendamentos.

    O relógio é fixado numa segunda-feira às 8h00m05s, para os testes não
    dependerem do dia e da hora em que rodam.

    English:
        Tests for the verificar_agendamentos task.

        The clock is pinned to a Monday at 8:00:05, so the tests do not
        depend on the day and time they run.
    """

    def setUp(self):
        """Cria robô, agendamento às 8h e o momento fixo do relógio.

        English:
            Creates a robot, an 8 a.m. schedule and the pinned clock time.
        """
        usuario = User.objects.create_user(
            username="analista", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-agendado",
            caminho_script="robo_exemplo.py",
            responsavel=usuario,
        )
        self.agendamento = Agendamento.objects.create(
            robo=self.robo, horario=time(8, 0)
        )
        self.agora = timezone.make_aware(datetime(2026, 9, 28, 8, 0, 5))

    def rodar_tarefa(self):
        """Roda a tarefa com o relógio fixado em self.agora.

        mock.patch.object troca timezone.localtime só dentro do bloco with; ao
        sair, a função original volta.

        English:
            Runs the task with the clock pinned to self.agora.

            mock.patch.object replaces timezone.localtime only inside the with
            block; on exit, the original function is restored.
        """
        with mock.patch.object(
            tasks.timezone, "localtime", return_value=self.agora
        ):
            return tasks.verificar_agendamentos()

    def test_dispara_no_minuto_certo(self):
        """Dispara no minuto certo, com origem agendamento.

        English:
            Fires at the right minute, with the schedule as its origin.
        """
        self.assertEqual(self.rodar_tarefa(), 1)

        execucao = self.robo.execucoes.get()
        self.assertEqual(execucao.origem, Execucao.Origem.AGENDAMENTO)
        self.assertEqual(execucao.agendamento, self.agendamento)

    def test_nao_dispara_duas_vezes_no_mesmo_minuto(self):
        """Rodar duas vezes no mesmo minuto dispara uma vez só.

        English:
            Running twice in the same minute fires only once.
        """
        self.rodar_tarefa()

        self.assertEqual(self.rodar_tarefa(), 0)
        self.assertEqual(self.robo.execucoes.count(), 1)

    def test_ignora_agendamento_pausado(self):
        """Agendamento pausado não dispara.

        English:
            A paused schedule does not fire.
        """
        self.agendamento.ativo = False
        self.agendamento.save()

        self.assertEqual(self.rodar_tarefa(), 0)

    def test_ignora_dia_desmarcado(self):
        """Dia desmarcado não dispara.

        English:
            An unchecked day does not fire.
        """
        self.agendamento.segunda = False
        self.agendamento.save()

        self.assertEqual(self.rodar_tarefa(), 0)

    def test_robo_em_manutencao_e_recusado_sem_quebrar_a_tarefa(self):
        """Robô em manutenção é recusado sem quebrar a tarefa.

        assertLogs confirma que a recusa foi registrada como aviso no log.

        English:
            A robot under maintenance is refused without breaking the task.

            assertLogs confirms the refusal was logged as a warning.
        """
        self.robo.status = Robo.Status.MANUTENCAO
        self.robo.save()

        with self.assertLogs("scheduler.tasks", level="WARNING"):
            self.assertEqual(self.rodar_tarefa(), 0)
        self.assertFalse(self.robo.execucoes.exists())


class ScheduleViewsTest(TestCase):
    """Testes das views de agendamentos.

    English:
        Tests for the schedule views.
    """

    def setUp(self):
        """Cria admin RPA com permissões, operador, robô e agendamento.

        English:
            Creates an RPA admin with permissions, an operator, a robot and a
            schedule.
        """
        self.client = Client()
        self.admin_rpa = User.objects.create_user(
            username="admin_rpa", password="senha123"
        )
        self.admin_rpa.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="scheduler")
        )
        self.operador = User.objects.create_user(
            username="operador", password="senha123"
        )
        self.robo = Robo.objects.create(
            nome="robo-agendado",
            caminho_script="robo_exemplo.py",
            responsavel=self.admin_rpa,
        )
        self.agendamento = Agendamento.objects.create(
            robo=self.robo, horario=time(8, 0)
        )

    def test_lista_redireciona_se_deslogado(self):
        """Quem não está logado é redirecionado (302) para o login.

        English:
            Anyone not logged in is redirected (302) to the login page.
        """
        response = self.client.get("/agendamentos/")
        self.assertEqual(response.status_code, 302)

    def test_lista_abre_para_quem_esta_logado(self):
        """Qualquer usuário logado vê a lista, mesmo sem permissões.

        English:
            Any logged-in user sees the list, even without permissions.
        """
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/agendamentos/")
        self.assertEqual(response.status_code, 200)

    def test_criar_registra_quem_criou(self):
        """Criar registra o usuário logado como criador.

        English:
            Creating records the logged-in user as the creator.
        """
        self.client.login(username="admin_rpa", password="senha123")
        self.client.post("/agendamentos/novo/", {
            "robo": self.robo.pk,
            "horario": "14:30",
            "segunda": "on",
            "ativo": "on",
        })

        criado = Agendamento.objects.get(horario=time(14, 30))
        self.assertEqual(criado.criado_por, self.admin_rpa)

    def test_criar_sem_permissao_recebe_403(self):
        """Sem permissão, a tela de criação responde 403.

        English:
            Without permission, the create page answers 403.
        """
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/agendamentos/novo/")
        self.assertEqual(response.status_code, 403)

    def test_pausar_inverte_o_ativo(self):
        """Alternar pausa um agendamento que estava ativo.

        English:
            Toggling pauses a schedule that was active.
        """
        self.client.login(username="admin_rpa", password="senha123")
        self.client.post(f"/agendamentos/{self.agendamento.pk}/alternar/")

        self.agendamento.refresh_from_db()
        self.assertFalse(self.agendamento.ativo)

    def test_excluir_mantem_as_execucoes_no_historico(self):
        """Excluir o agendamento mantém as execuções, só sem a referência.

        English:
            Deleting the schedule keeps the executions, just without the
            reference.
        """
        execucao = Execucao.objects.create(
            robo=self.robo, agendamento=self.agendamento
        )
        self.client.login(username="admin_rpa", password="senha123")

        self.client.post(f"/agendamentos/{self.agendamento.pk}/excluir/")

        self.assertFalse(
            Agendamento.objects.filter(pk=self.agendamento.pk).exists()
        )
        execucao.refresh_from_db()
        self.assertIsNone(execucao.agendamento)
