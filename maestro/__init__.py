"""Pacote principal do projeto Maestro.

Importar o app do Celery aqui garante que ele seja carregado junto com
o Django. Assim, o decorator ``@shared_task`` usado nos apps encontra
a aplicação Celery certa assim que o projeto sobe.

English:
    Main package of the Maestro project.

    Importing the Celery app here ensures it is loaded together with
    Django. That way, the ``@shared_task`` decorator used in the apps
    finds the right Celery application as soon as the project starts.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
