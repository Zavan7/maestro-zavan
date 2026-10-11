#!/usr/bin/env python
"""Utilitário de linha de comando do Django para tarefas administrativas.

É por ele que rodamos o servidor (``runserver``), os testes
(``test``), as migrations (``makemigrations`` e ``migrate``) e
qualquer outro comando do Django.

English:
    Django's command-line utility for administrative tasks.

    It is how we run the server (``runserver``), the tests (``test``),
    the migrations (``makemigrations`` and ``migrate``) and any other
    Django command.
"""
import os
import sys


def main():
    """Configura o Django e executa o comando pedido na linha de comando.

    Antes de tudo, define a variável ``DJANGO_SETTINGS_MODULE`` para que o
    Django saiba qual arquivo de configurações usar. Se o Django não estiver
    instalado, mostra uma mensagem que ajuda a lembrar de ativar o ambiente
    virtual (no nosso caso, rodar com ``uv run``).

    Raises:
        ImportError: se o Django não puder ser importado.

    English:
        Sets up Django and runs the command given on the command line.

        First, it sets the ``DJANGO_SETTINGS_MODULE`` variable so Django
        knows which settings file to use. If Django is not installed, it
        shows a message reminding you to activate the virtual environment
        (in our case, run with ``uv run``).

        Raises:
            ImportError: if Django cannot be imported.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maestro.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
