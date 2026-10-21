"""Rotas de WebSocket do app de execuções.

Esta rota é aberta pelo navegador, então leva as duas proteções do
navegador: ``AllowedHostsOriginValidator`` recusa conexões vindas de
sites fora do ``ALLOWED_HOSTS`` (a mesma proteção que o CSRF dá aos
formulários) e ``AuthMiddlewareStack`` lê a sessão do Django e preenche
``scope["user"]``.

English:
    WebSocket routes for the executions app.

    This route is opened by the browser, so it carries both browser
    protections: ``AllowedHostsOriginValidator`` refuses connections from
    sites outside ``ALLOWED_HOSTS`` (the same protection CSRF gives
    forms) and ``AuthMiddlewareStack`` reads the Django session and fills
    ``scope["user"]``.
"""

from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path

from executions.consumers import ExecucaoConsumer

websocket_urlpatterns = [
    path(
        "ws/execucoes/<int:pk>/",
        AllowedHostsOriginValidator(
            AuthMiddlewareStack(ExecucaoConsumer.as_asgi())
        ),
    ),
]
