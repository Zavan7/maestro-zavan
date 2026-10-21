"""Rotas de WebSocket do projeto, reunindo as de cada app.

Cada app decide as proteções da própria rota: a do navegador usa sessão
e validação de origem; a do agente, token.

English:
    Project WebSocket routes, gathering each app's routes.

    Each app decides its own route's protections: the browser one uses
    session and origin validation; the agent one, a token.
"""

from agents.routing import websocket_urlpatterns as rotas_agentes
from executions.routing import websocket_urlpatterns as rotas_execucoes

websocket_urlpatterns = [*rotas_execucoes, *rotas_agentes]
