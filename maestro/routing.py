"""Rotas de WebSocket do projeto, reunindo as de cada app.

English:
    Project WebSocket routes, gathering each app's routes.
"""

from executions.routing import websocket_urlpatterns as rotas_execucoes

websocket_urlpatterns = [*rotas_execucoes]
