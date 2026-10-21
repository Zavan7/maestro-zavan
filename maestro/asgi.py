"""Configuração ASGI do projeto Maestro.

ASGI é a interface entre servidores web assíncronos (como o Daphne) e o
Django. O ``ProtocolTypeRouter`` separa o tráfego pelo tipo: ``http``
segue para o Django de sempre, e ``websocket`` para as rotas de
``maestro.routing``. Cada rota de WebSocket leva a própria proteção
(sessão e origem para o navegador, token para o agente), porque um
validador de origem aqui na frente recusaria o agente, que não é um
navegador.

``get_asgi_application()`` precisa rodar antes de importar as rotas,
porque ele configura o Django, e as rotas importam models.

English:
    ASGI configuration for the Maestro project.

    ASGI is the interface between asynchronous web servers (such as
    Daphne) and Django. ``ProtocolTypeRouter`` splits traffic by type:
    ``http`` goes to the usual Django, and ``websocket`` to the
    ``maestro.routing`` routes. Each WebSocket route carries its own
    protection (session and origin for the browser, token for the
    agent), because an origin validator up front would refuse the agent,
    which is not a browser.

    ``get_asgi_application()`` must run before importing the routes,
    because it sets Django up, and the routes import models.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from maestro.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(
            websocket_urlpatterns  # type: ignore[arg-type]
        ),
    }
)
