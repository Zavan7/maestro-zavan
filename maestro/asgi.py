"""Configuração ASGI do projeto Maestro.

ASGI é a interface entre servidores web assíncronos (como Daphne ou
Uvicorn) e o Django. Ela será importante quando o Maestro usar
WebSocket para falar com o agente em Go. O servidor procura a variável
``application`` neste módulo.

Mais informações em
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/

English:
    ASGI configuration for the Maestro project.

    ASGI is the interface between asynchronous web servers (such as
    Daphne or Uvicorn) and Django. It will matter when Maestro uses
    WebSocket to talk to the Go agent. The server looks for the
    ``application`` variable in this module.

    More information at
    https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")

application = get_asgi_application()
