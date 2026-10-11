"""Configuração WSGI do projeto Maestro.

WSGI é a interface clássica (síncrona) entre servidores web, como o
Gunicorn, e o Django. O servidor procura a variável ``application``
neste módulo para atender as requisições.

Mais informações em
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/

English:
    WSGI configuration for the Maestro project.

    WSGI is the classic (synchronous) interface between web servers,
    such as Gunicorn, and Django. The server looks for the
    ``application`` variable in this module to handle requests.

    More information at
    https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")

application = get_wsgi_application()
