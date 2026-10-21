"""Rotas de WebSocket do app de execuções.

English:
    WebSocket routes for the executions app.
"""

from django.urls import path

from executions.consumers import ExecucaoConsumer

# Os stubs do Django tipam o path() só para views HTTP; o Channels usa o
# mesmo path() com apps ASGI.
websocket_urlpatterns = [
    path(
        "ws/execucoes/<int:pk>/",
        ExecucaoConsumer.as_asgi(),  # type: ignore[arg-type]
    ),
]
