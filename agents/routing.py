"""Rotas de WebSocket do app de agentes.

O agente não é um navegador: não manda ``Origin`` nem tem sessão. Por
isso esta rota não passa pelo validador de origem nem pela sessão; a
autenticação é o token, conferido no ``AgenteConsumer``.

English:
    WebSocket routes for the agents app.

    The agent is not a browser: it sends no ``Origin`` and has no
    session. That is why this route skips the origin validator and the
    session; authentication is the token, checked in ``AgenteConsumer``.
"""

from django.urls import path

from agents.consumers import AgenteConsumer

# Os stubs do Django tipam o path() só para views HTTP; o Channels usa o
# mesmo path() com apps ASGI.
websocket_urlpatterns = [
    path(
        "ws/agente/",
        AgenteConsumer.as_asgi(),  # type: ignore[arg-type]
    ),
]
