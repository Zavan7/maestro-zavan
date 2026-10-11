"""Configurações do Django para o projeto Maestro.

Tudo o que é sensível (como a ``SECRET_KEY``) ou muda de um ambiente
para outro (como ``DEBUG`` e ``ALLOWED_HOSTS``) vem do arquivo ``.env``,
que fica fora do Git. Assim o mesmo código serve para desenvolvimento e
produção sem expor segredos.

English:
    Django settings for the Maestro project.

    Everything sensitive (such as ``SECRET_KEY``) or that changes from
    one environment to another (such as ``DEBUG`` and
    ``ALLOWED_HOSTS``) comes from the ``.env`` file, which is kept out
    of Git. That way the same code works in development and production
    without exposing secrets.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(nome, padrao="False"):
    """Lê uma variável de ambiente e a converte em booleano.

    Variáveis de ambiente são sempre texto, então ``DEBUG=False`` chega
    como a string ``"False"``, que em Python é verdadeira! Esta função
    resolve isso: só ``true`` ou ``1`` (sem diferenciar maiúsculas e
    ignorando espaços) viram ``True``; qualquer outro valor vira ``False``.

    Args:
        nome: nome da variável de ambiente, por exemplo ``"DEBUG"``.
        padrao: texto usado quando a variável não existe.

    Returns:
        ``True`` se o valor for ``true`` ou ``1``; ``False`` caso contrário.

    English:
        Reads an environment variable and converts it to a boolean.

        Environment variables are always text, so ``DEBUG=False`` arrives
        as the string ``"False"``, which is truthy in Python! This function
        fixes that: only ``true`` or ``1`` (case-insensitive, ignoring
        spaces) become ``True``; any other value becomes ``False``.

        Args:
            nome: name of the environment variable, e.g. ``"DEBUG"``.
            padrao: text used when the variable does not exist.

        Returns:
            ``True`` if the value is ``true`` or ``1``; ``False``
            otherwise.
    """
    return os.getenv(nome, padrao).strip().lower() in ("true", "1")


def env_lista(nome, padrao=""):
    """Lê uma variável de ambiente separada por vírgulas como lista.

    Útil para ``ALLOWED_HOSTS``: ``"localhost, 127.0.0.1,"`` vira
    ``["localhost", "127.0.0.1"]``. Os espaços nas pontas de cada item são
    removidos e itens vazios (como o depois da última vírgula) são
    descartados.

    Args:
        nome: nome da variável de ambiente.
        padrao: texto usado quando a variável não existe.

    Returns:
        Lista de strings, sem espaços nas pontas e sem itens vazios.

    English:
        Reads a comma-separated environment variable as a list.

        Handy for ``ALLOWED_HOSTS``: ``"localhost, 127.0.0.1,"`` becomes
        ``["localhost", "127.0.0.1"]``. Leading and trailing spaces are
        stripped from each item and empty items (like the one after the
        last comma) are dropped.

        Args:
            nome: name of the environment variable.
            padrao: text used when the variable does not exist.

        Returns:
            List of strings, stripped and without empty items.
    """
    return [
        item.strip()
        for item in os.getenv(nome, padrao).split(",")
        if item.strip()
    ]


# Segurança
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = env_bool("DEBUG")
ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS")


# Aplicações
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "executions",
    "robots",
    "scheduler",
    "config",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "maestro.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "maestro.wsgi.application"


# Banco de dados
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Senhas
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation.NumericPasswordValidator"
        ),
    },
]


# Autenticação
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "portfolio"


# Internacionalização
LANGUAGE_CODE = "pt-BR"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# Arquivos estáticos
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]


# E-mail
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# Celery e execução de robôs
CELERY_BROKER_URL = os.getenv(
    "CELERY_BROKER_URL", "redis://localhost:6379/0"
)
ROBOS_SCRIPTS_DIR = Path(
    os.getenv("ROBOS_SCRIPTS_DIR", BASE_DIR / "scripts")
)
CELERY_TIMEZONE = TIME_ZONE
