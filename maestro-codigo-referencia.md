# Maestro — Código de Referência por Etapa

> Não é pra copiar tudo de uma vez — use como consulta enquanto for implementando cada etapa do roteiro. Os nomes de campos/apps seguem exatamente o que já existe no projeto.

---

## Etapa 1 — DEBUG e EMAIL_BACKEND

### `settings.py`

```python
# Antes:
# DEBUG = os.getenv('DEBUG')

# Depois:
DEBUG = os.getenv('DEBUG', 'False') == 'True'
```

```python
# Antes:
# MAILERS = {
#     'default': {
#         'BACKEND': 'django.core.mail.backends.console.EmailBackend',
#     },
# }

# Depois:
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### `.env.example`

```
SECRET_KEY=troque-por-uma-chave-gerada
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
```

---

## Etapa 2 — `ModelForm` para robôs

### `robots/forms.py` (arquivo novo)

```python
from django import forms
from robots.models import Robo


class RoboForm(forms.ModelForm):
    class Meta:
        model = Robo
        fields = ["nome", "descricao", "caminho_script", "status"]
```

### `robots/views.py` (substitui `robot_create` e `robot_edit`)

```python
from robots.forms import RoboForm


@login_required
def robot_create(request):
    if request.method == "POST":
        form = RoboForm(request.POST)
        if form.is_valid():
            robo = form.save(commit=False)
            robo.responsavel = request.user
            robo.save()
            return redirect("robot_list")
    else:
        form = RoboForm()

    return render(request, "robots/create.html", {"form": form})


@login_required
def robot_edit(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        form = RoboForm(request.POST, instance=robo)
        if form.is_valid():
            form.save()
            return redirect("robot_list")
    else:
        form = RoboForm(instance=robo)

    return render(request, "robots/edit.html", {"form": form, "robo": robo})
```

**Nota:** `commit=False` no create segura o save pra dar tempo de setar `responsavel` (que não é campo do form, é preenchido pelo backend). No edit, `instance=robo` faz o form vir preenchido com os dados atuais.

### `templates/robots/create.html` (campo por campo, mantendo o estilo atual)

```django-html
<form method="post" class="form-card">
  {% csrf_token %}

  <label class="field-label">nome</label>
  {{ form.nome }}
  {% if form.nome.errors %}<p class="error-message">{{ form.nome.errors.0 }}</p>{% endif %}

  <label class="field-label">descrição</label>
  {{ form.descricao }}

  <label class="field-label">caminho do script</label>
  {{ form.caminho_script }}
  {% if form.caminho_script.errors %}<p class="error-message">{{ form.caminho_script.errors.0 }}</p>{% endif %}

  <label class="field-label">status</label>
  {{ form.status }}

  <button type="submit" class="btn">cadastrar</button>
</form>
```

**Nota:** `edit.html` é idêntico, só troca o texto do botão e o `{% block title %}`.

---

## Etapa 3 — Testes das views

### `robots/tests.py` (adiciona à classe de testes existente, ou cria `RobotViewsTest`)

```python
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from robots.models import Robo
from executions.models import Execucao

User = get_user_model()


class RobotViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.usuario = User.objects.create_user(username="analista", password="senha123")
        self.robo = Robo.objects.create(
            nome="robo-teste",
            caminho_script="/scripts/teste.py",
            responsavel=self.usuario,
        )

    def test_robot_list_redireciona_se_deslogado(self):
        response = self.client.get("/robots/")
        self.assertEqual(response.status_code, 302)

    def test_robot_list_retorna_200_logado(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/robots/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "robo-teste")

    def test_robot_edit_salva_alteracoes(self):
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
        Execucao.objects.create(robo=self.robo)
        self.client.login(username="analista", password="senha123")
        response = self.client.post(f"/robots/{self.robo.pk}/excluir/", follow=True)
        self.assertTrue(Robo.objects.filter(pk=self.robo.pk).exists())
        self.assertContains(response, "Não é possível excluir")

    def test_robot_exclusion_funciona_sem_execucao(self):
        self.client.login(username="analista", password="senha123")
        self.client.post(f"/robots/{self.robo.pk}/excluir/")
        self.assertFalse(Robo.objects.filter(pk=self.robo.pk).exists())
```

### `executions/tests.py` (testes de views, além dos testes de model existentes)

```python
class ExecutionViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.usuario = User.objects.create_user(username="analista", password="senha123")
        self.robo = Robo.objects.create(
            nome="robo-teste", caminho_script="/x.py", responsavel=self.usuario
        )
        self.execucao = Execucao.objects.create(robo=self.robo, log="linha 1\nlinha 2")

    def test_execution_detail_mostra_log(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get(f"/execucoes/{self.execucao.pk}/")
        self.assertContains(response, "linha 1")

    def test_execution_detail_404_para_pk_inexistente(self):
        self.client.login(username="analista", password="senha123")
        response = self.client.get("/execucoes/99999/")
        self.assertEqual(response.status_code, 404)
```

---

## Etapa 4 — Groups e Permissions

### Criar grupos (via shell: `uv run manage.py shell`)

```python
from django.contrib.auth.models import Group, Permission

operador, _ = Group.objects.get_or_create(name="Operador")
admin_rpa, _ = Group.objects.get_or_create(name="Administrador RPA")

# Operador só inicia/para execução — não precisa de permissão especial
# de model pra isso (a view controla), mas Administrador ganha
# as permissões padrão de Robo:
permissoes_robo = Permission.objects.filter(content_type__app_label="robots")
admin_rpa.permissions.set(permissoes_robo)
```

### `robots/views.py`

```python
from django.contrib.auth.decorators import permission_required


@permission_required("robots.delete_robo", raise_exception=True)
def robot_exclusion(request, pk):
    ...


@permission_required("robots.add_robo", raise_exception=True)
def robot_create(request):
    ...


@permission_required("robots.change_robo", raise_exception=True)
def robot_edit(request, pk):
    ...
```

**Nota:** `raise_exception=True` faz devolver 403 (proibido) pra quem já está logado mas sem permissão, em vez de redirecionar pro login (que seria enganoso — a pessoa já está autenticada).

### Front — esconder ação sem permissão (cosmético, não é a proteção real)

```django-html
{% if perms.robots.delete_robo %}
  <a href="{% url 'robot_exclusion' robo.id %}" class="link-btn">excluir</a>
{% endif %}
```

---

## Etapa 5 — Celery + Redis

### Instalação

```bash
uv add celery redis django-celery-results
```

### `maestro/celery.py` (arquivo novo)

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")

app = Celery("maestro")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### `maestro/__init__.py`

```python
from .celery import app as celery_app

__all__ = ("celery_app",)
```

### `settings.py`

```python
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
INSTALLED_APPS += ["django_celery_results"]
```

### `robots/tasks.py` (arquivo novo)

```python
import subprocess
from celery import shared_task
from django.utils import timezone
from executions.models import Execucao


@shared_task
def executar_robo(execucao_id):
    execucao = Execucao.objects.get(pk=execucao_id)
    execucao.iniciado_em = timezone.now()
    execucao.save()

    try:
        resultado = subprocess.run(
            ["python", execucao.robo.caminho_script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        execucao.log = (resultado.stdout + resultado.stderr)[:10000]
        execucao.status = (
            Execucao.Status.SUCESSO if resultado.returncode == 0 else Execucao.Status.FALHA
        )
    except subprocess.TimeoutExpired:
        execucao.log = "Execução excedeu o tempo limite."
        execucao.status = Execucao.Status.FALHA

    execucao.finalizado_em = timezone.now()
    execucao.save()
```

**Nota:** repare no `["python", execucao.robo.caminho_script]` — lista de argumentos, nunca `shell=True` com string concatenada. E `[:10000]` limita o tamanho do log salvo.

### `robots/views.py` (ajusta `robot_start`)

```python
from robots.tasks import executar_robo


@login_required
def robot_start(request, pk):
    robo = get_object_or_404(Robo, pk=pk)

    if request.method == "POST":
        ja_rodando = robo.execucoes.filter(status=Execucao.Status.RODANDO).exists()
        if not ja_rodando:
            execucao = Execucao.objects.create(
                robo=robo,
                status=Execucao.Status.RODANDO,
                disparado_por=request.user,
            )
            executar_robo.delay(execucao.id)

    return redirect("robot_list")
```

### Rodar o worker (processo separado do `runserver`)

```bash
uv run celery -A maestro worker --loglevel=info
```

---

## Etapa 6 — Agendamento (`django-celery-beat`)

### Instalação

```bash
uv add django-celery-beat
```

### `settings.py`

```python
INSTALLED_APPS += ["django_celery_beat"]
```

```bash
uv run manage.py migrate
```

### Criar agendamento (via shell, ou construa uma tela depois)

```python
from django_celery_beat.models import PeriodicTask, CrontabSchedule

schedule, _ = CrontabSchedule.objects.get_or_create(
    minute="0", hour="8", day_of_week="1"  # toda segunda às 8h
)

PeriodicTask.objects.create(
    crontab=schedule,
    name="Rodar robo-teste semanalmente",
    task="robots.tasks.executar_robo",
    args='[1]',  # id da execução — normalmente você criaria a Execucao antes
)
```

### Rodar o beat (mais um processo separado)

```bash
uv run celery -A maestro beat --loglevel=info
```

---

## Etapa 7 — API REST (DRF)

### Instalação

```bash
uv add djangorestframework djangorestframework-simplejwt
```

### `settings.py`

```python
INSTALLED_APPS += ["rest_framework"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "100/hour",
    },
}
```

### `robots/serializers.py` (arquivo novo)

```python
from rest_framework import serializers
from robots.models import Robo


class RoboSerializer(serializers.ModelSerializer):
    class Meta:
        model = Robo
        fields = ["id", "nome", "descricao", "status", "criado_em"]
        read_only_fields = ["id", "criado_em"]
```

### `robots/api_views.py` (arquivo novo, separado das views de template)

```python
from rest_framework import viewsets
from robots.models import Robo
from robots.serializers import RoboSerializer


class RoboViewSet(viewsets.ModelViewSet):
    queryset = Robo.objects.all()
    serializer_class = RoboSerializer

    def perform_create(self, serializer):
        serializer.save(responsavel=self.request.user)
```

### `maestro/urls.py`

```python
from rest_framework.routers import DefaultRouter
from robots.api_views import RoboViewSet
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

router = DefaultRouter()
router.register("robos", RoboViewSet)

urlpatterns += [
    path("api/", include(router.urls)),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
```

---

## Etapa 8 — Isolamento via Docker

### Instalação

```bash
uv add docker
```

### `robots/tasks.py` (versão com container, substituindo o `subprocess` direto)

```python
import docker
from celery import shared_task
from django.utils import timezone
from executions.models import Execucao


@shared_task
def executar_robo(execucao_id):
    execucao = Execucao.objects.get(pk=execucao_id)
    execucao.iniciado_em = timezone.now()
    execucao.save()

    client = docker.from_env()

    try:
        output = client.containers.run(
            image="python:3.12-slim",
            command=["python", "/app/script.py"],
            volumes={execucao.robo.caminho_script: {"bind": "/app/script.py", "mode": "ro"}},
            mem_limit="256m",
            cpu_quota=50000,  # 50% de 1 CPU
            network_disabled=True,
            remove=True,
            stderr=True,
        )
        execucao.log = output.decode()[:10000]
        execucao.status = Execucao.Status.SUCESSO
    except docker.errors.ContainerError as e:
        execucao.log = str(e)[:10000]
        execucao.status = Execucao.Status.FALHA

    execucao.finalizado_em = timezone.now()
    execucao.save()
```

**Nota:** `network_disabled=True` bloqueia acesso à rede por padrão — ajuste conforme o robô precisar de internet ou não (idealmente, whitelist específica em vez de liberar tudo).

---

## Etapa 9 — Agente em Go (esqueleto inicial)

### Instalação Django (WebSocket via Channels)

```bash
uv add channels channels-redis
```

### `maestro/asgi.py`

```python
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from robots.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": URLRouter(websocket_urlpatterns),
})
```

### `robots/consumers.py` (arquivo novo — recebe conexão do agente)

```python
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class AgentConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive(self, text_data):
        data = json.loads(text_data)
        # data esperado: {"execucao_id": ..., "status": ..., "log": ...}
        # aqui você atualizaria a Execucao correspondente
```

### Esqueleto do agente em Go (`main.go`, projeto separado)

```go
package main

import (
    "log"
    "net/url"
    "os/exec"

    "github.com/gorilla/websocket"
)

func main() {
    u := url.URL{Scheme: "ws", Host: "localhost:8000", Path: "/ws/agent/"}
    conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
    if err != nil {
        log.Fatal("erro ao conectar:", err)
    }
    defer conn.Close()

    for {
        _, message, err := conn.ReadMessage()
        if err != nil {
            log.Println("conexão encerrada:", err)
            return
        }

        // comando recebido (ex: caminho do script a rodar)
        cmd := exec.Command("python", string(message))
        output, _ := cmd.CombinedOutput()

        conn.WriteMessage(websocket.TextMessage, output)
    }
}
```

**Nota:** isso é um ponto de partida mínimo, sem autenticação do agente nem tratamento de erro robusto — o roteiro já avisa: valide identidade do agente antes de aceitar comandos dele.

---

## Etapa 10 — Observabilidade e auditoria

### Instalação

```bash
uv add sentry-sdk django-simple-history
```

### `settings.py`

```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
)

INSTALLED_APPS += ["simple_history"]
MIDDLEWARE += ["simple_history.middleware.HistoryRequestMiddleware"]
```

### `robots/models.py` (adiciona histórico ao model existente)

```python
from simple_history.models import HistoricalRecords


class Robo(models.Model):
    # ...campos existentes...
    history = HistoricalRecords()
```

```bash
uv run manage.py makemigrations robots
uv run manage.py migrate
```

**Nota:** isso cria automaticamente uma tabela paralela guardando cada versão do `Robo` ao longo do tempo — consulta via `robo.history.all()`.

### Headers de segurança em `settings.py` (produção)

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
X_FRAME_OPTIONS = "DENY"
```

---

## Lembrete final

Cada bloco acima é ponto de partida, não código de produção pronto — ajuste nomes, trate mais casos de erro, e sempre teste antes de considerar uma etapa "concluída" no Trello.
