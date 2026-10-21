"""Configuração ASGI do projeto Maestro.

ASGI é a interface entre servidores web assíncronos (como o Daphne) e o
Django. O ``ProtocolTypeRouter`` separa o tráfego pelo tipo:

- ``http`` segue para o Django de sempre;
- ``websocket`` passa por duas camadas antes das rotas: o
  ``AllowedHostsOriginValidator`` recusa conexões vindas de sites fora
  do ``ALLOWED_HOSTS`` (a mesma proteção que o CSRF dá aos formulários),
  e o ``AuthMiddlewareStack`` lê a sessão do Django e preenche
  ``scope["user"]``.

``get_asgi_application()`` precisa rodar antes de importar as rotas,
porque ele configura o Django, e as rotas importam models.

English:
    ASGI configuration for the Maestro project.

    ASGI is the interface between asynchronous web servers (such as
    Daphne) and Django. ``ProtocolTypeRouter`` splits traffic by type:

    - ``http`` goes to the usual Django;
    - ``websocket`` goes through two layers before the routes:
      ``AllowedHostsOriginValidator`` refuses connections from sites
      outside ``ALLOWED_HOSTS`` (the same protection CSRF gives forms),
      and ``AuthMiddlewareStack`` reads the Django session and fills
      ``scope["user"]``.

    ``get_asgi_application()`` must run before importing the routes,
    because it sets Django up, and the routes import models.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import (  # noqa: E402
    AllowedHostsOriginValidator,
)

from maestro.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(websocket_urlpatterns)  # type: ignore[arg-type]
            )
        ),
    }
)
