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
    return {dia: dia in marcados for dia in DIAS_DA_SEMANA}


class AgendamentoModelTest(TestCase):
    def setUp(self):
        usuario = User.objects.create_user(username="analista", password="senha123")
        self.robo = Robo.objects.create(
            nome="robo-agendado", caminho_script="robo_exemplo.py", responsavel=usuario
        )

    def test_recusa_agendamento_sem_nenhum_dia(self):
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0), **dias())

        with self.assertRaises(ValidationError):
            agendamento.full_clean()

    def test_save_zera_os_segundos(self):
        agendamento = Agendamento.objects.create(robo=self.robo, horario=time(8, 0, 30))

        agendamento.refresh_from_db()
        self.assertEqual(agendamento.horario, time(8, 0))

    def test_dias_formatados(self):
        uteis = Agendamento(robo=self.robo, horario=time(8, 0))
        todos = Agendamento(robo=self.robo, horario=time(9, 0), **dias(*DIAS_DA_SEMANA))
        alguns = Agendamento(robo=self.robo, horario=time(10, 0), **dias("segunda", "sabado"))

        self.assertEqual(uteis.dias_formatados(), "dias úteis")
        self.assertEqual(todos.dias_formatados(), "todos os dias")
        self.assertEqual(alguns.dias_formatados(), "seg, sáb")

    def test_proxima_ocorrencia_ainda_hoje(self):
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0))

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_7H)

        self.assertEqual(proxima, timezone.make_aware(datetime(2026, 9, 28, 8, 0)))

    def test_proxima_ocorrencia_quando_o_horario_ja_passou(self):
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0))

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_9H)

        self.assertEqual(proxima, timezone.make_aware(datetime(2026, 9, 29, 8, 0)))

    def test_proxima_ocorrencia_pula_dias_desmarcados(self):
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0), **dias("sexta"))

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_7H)

        self.assertEqual(proxima, timezone.make_aware(datetime(2026, 10, 2, 8, 0)))

    def test_proxima_ocorrencia_no_mesmo_dia_da_semana_seguinte(self):
        agendamento = Agendamento(robo=self.robo, horario=time(8, 0), **dias("segunda"))

        proxima = agendamento.proxima_ocorrencia(SEGUNDA_9H)

        self.assertEqual(proxima, timezone.make_aware(datetime(2026, 10, 5, 8, 0)))

    def test_formatar_proxima(self):
        hoje = timezone.make_aware(datetime(2026, 9, 28, 8, 0))
        amanha = timezone.make_aware(datetime(2026, 9, 29, 8, 0))
        sexta = timezone.make_aware(datetime(2026, 10, 2, 8, 0))

        self.assertEqual(formatar_proxima(hoje, SEGUNDA_7H), "hoje 08:00")
        self.assertEqual(formatar_proxima(amanha, SEGUNDA_7H), "amanhã 08:00")
        self.assertEqual(formatar_proxima(sexta, SEGUNDA_7H), "sex 08:00")


class VerificarAgendamentosTest(TestCase):
    def setUp(self):
        usuario = User.objects.create_user(username="analista", password="senha123")
        self.robo = Robo.objects.create(
            nome="robo-agendado", caminho_script="robo_exemplo.py", responsavel=usuario
        )
        self.agendamento = Agendamento.objects.create(robo=self.robo, horario=time(8, 0))
        self.agora = timezone.make_aware(datetime(2026, 9, 28, 8, 0, 5))

    def rodar_tarefa(self):
        with mock.patch.object(tasks.timezone, "localtime", return_value=self.agora):
            return tasks.verificar_agendamentos()

    def test_dispara_no_minuto_certo(self):
        self.assertEqual(self.rodar_tarefa(), 1)

        execucao = self.robo.execucoes.get()
        self.assertEqual(execucao.origem, Execucao.Origem.AGENDAMENTO)
        self.assertEqual(execucao.agendamento, self.agendamento)

    def test_nao_dispara_duas_vezes_no_mesmo_minuto(self):
        self.rodar_tarefa()

        self.assertEqual(self.rodar_tarefa(), 0)
        self.assertEqual(self.robo.execucoes.count(), 1)

    def test_ignora_agendamento_pausado(self):
        self.agendamento.ativo = False
        self.agendamento.save()

        self.assertEqual(self.rodar_tarefa(), 0)

    def test_ignora_dia_desmarcado(self):
        self.agendamento.segunda = False
        self.agendamento.save()

        self.assertEqual(self.rodar_tarefa(), 0)

    def test_robo_em_manutencao_e_recusado_sem_quebrar_a_tarefa(self):
        self.robo.status = Robo.Status.MANUTENCAO
        self.robo.save()

        with self.assertLogs("scheduler.tasks", level="WARNING"):
            self.assertEqual(self.rodar_tarefa(), 0)
        self.assertFalse(self.robo.execucoes.exists())


class ScheduleViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_rpa = User.objects.create_user(username="admin_rpa", password="senha123")
        self.admin_rpa.user_permissions.add(
            *Permission.objects.filter(content_type__app_label="scheduler")
        )
        self.operador = User.objects.create_user(username="operador", password="senha123")
        self.robo = Robo.objects.create(
            nome="robo-agendado", caminho_script="robo_exemplo.py", responsavel=self.admin_rpa
        )
        self.agendamento = Agendamento.objects.create(robo=self.robo, horario=time(8, 0))

    def test_lista_redireciona_se_deslogado(self):
        response = self.client.get("/agendamentos/")
        self.assertEqual(response.status_code, 302)

    def test_lista_abre_para_quem_esta_logado(self):
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/agendamentos/")
        self.assertEqual(response.status_code, 200)

    def test_criar_registra_quem_criou(self):
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
        self.client.login(username="operador", password="senha123")
        response = self.client.get("/agendamentos/novo/")
        self.assertEqual(response.status_code, 403)

    def test_pausar_inverte_o_ativo(self):
        self.client.login(username="admin_rpa", password="senha123")
        self.client.post(f"/agendamentos/{self.agendamento.pk}/alternar/")

        self.agendamento.refresh_from_db()
        self.assertFalse(self.agendamento.ativo)

    def test_excluir_mantem_as_execucoes_no_historico(self):
        execucao = Execucao.objects.create(robo=self.robo, agendamento=self.agendamento)
        self.client.login(username="admin_rpa", password="senha123")

        self.client.post(f"/agendamentos/{self.agendamento.pk}/excluir/")

        self.assertFalse(Agendamento.objects.filter(pk=self.agendamento.pk).exists())
        execucao.refresh_from_db()
        self.assertIsNone(execucao.agendamento)
