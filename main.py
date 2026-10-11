"""Ponto de entrada gerado automaticamente pelo ``uv init``.

O Maestro não é iniciado por aqui: como todo projeto Django, ele roda
pelo ``manage.py`` (por exemplo, ``uv run manage.py runserver``). Este
arquivo ficou só como resquício da criação do projeto.

English:
    Entry point generated automatically by ``uv init``.

    Maestro is not started from here: like any Django project, it runs
    through ``manage.py`` (for example, ``uv run manage.py runserver``).
    This file is just a leftover from the project's creation.
"""


def main():
    """Exibe uma saudação simples no terminal.

    Serve apenas para confirmar que o pacote está instalado e que o
    Python consegue executá-lo.

    English:
        Prints a simple greeting to the terminal.

        It only serves to confirm that the package is installed and that
        Python can run it.
    """
    print("Hello from azav-maestro!")


if __name__ == "__main__":
    main()
