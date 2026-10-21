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
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(nome: str, padrao: str = "False") -> bool:
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


def env_lista(nome: str, padrao: str = "") -> list[str]:
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


def ler_secret_key(debug: bool, executando_testes: bool) -> str:
    """Lê a ``SECRET_KEY`` do ambiente, com uma chave fixa só para dev.

    Em desenvolvimento (``DEBUG`` ligado) e nos testes, uma chave fixa e
    pública basta: ela não protege nada real, e assim um clone novo roda
    ``manage.py test`` sem precisar de ``.env``. Fora disso, a falta da
    chave é um erro de configuração e o Maestro nem sobe, em vez de
    falhar mais tarde, na primeira sessão ou mensagem assinada.

    Args:
        debug: valor de ``DEBUG`` já lido do ambiente.
        executando_testes: se o comando atual é ``manage.py test``.

    Returns:
        A chave do ambiente ou, em dev e testes, a chave fixa.

    Raises:
        ImproperlyConfigured: se a chave falta fora de dev e testes.

    English:
        Reads ``SECRET_KEY`` from the environment, with a fixed dev key.

        In development (``DEBUG`` on) and in tests, a fixed public key is
        enough: it protects nothing real, and a fresh clone can run
        ``manage.py test`` without a ``.env``. Otherwise, a missing key is
        a configuration error and Maestro does not even start, instead of
        failing later, on the first session or signed message.

        Args:
            debug: ``DEBUG`` value already read from the environment.
            executando_testes: whether the current command is
                ``manage.py test``.

        Returns:
            The key from the environment or, in dev and tests, the fixed
            key.

        Raises:
            ImproperlyConfigured: if the key is missing outside dev and
                tests.
    """
    chave = os.getenv("SECRET_KEY", "").strip()
    if chave:
        return chave
    if debug or executando_testes:
        return "django-insecure-chave-fixa-so-para-desenvolvimento"
    raise ImproperlyConfigured(
        "Defina SECRET_KEY no .env (veja o .env.example)."
    )


# Segurança
DEBUG = env_bool("DEBUG")
EXECUTANDO_TESTES = sys.argv[1:2] == ["test"]
SECRET_KEY = ler_secret_key(DEBUG, executando_testes=EXECUTANDO_TESTES)
ALLOWED_HOSTS = env_lista("ALLOWED_HOSTS")


# Aplicações
# O daphne vem primeiro para o runserver dele substituir o do Django e
# atender HTTP e WebSocket.
INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "accounts",
    "executions",
    "robots",
    "scheduler",
    "config",
    "agents",
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
# Com o log ao vivo, o worker grava enquanto a tela lê. No SQLite, o modo
# WAL deixa leitura e escrita acontecerem juntas, e o timeout faz quem
# encontrar o banco ocupado esperar em vez de falhar com "database is
# locked". Em produção, o caminho é o PostgreSQL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL;",
            "transaction_mode": "IMMEDIATE",
        },
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
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
# ``or``, e não o padrão do ``getenv``: ``ROBOS_SCRIPTS_DIR=`` vazio no
# ``.env`` viraria ``Path("")``, a pasta de onde o worker foi iniciado.
ROBOS_SCRIPTS_DIR = Path(
    os.getenv("ROBOS_SCRIPTS_DIR", "").strip() or BASE_DIR / "scripts"
)
CELERY_TIMEZONE = TIME_ZONE


# Django Channels: WebSocket do log ao vivo
# O Redis do Channels usa o banco 1, separado da fila do Celery (banco 0).
# Nos testes, a camada em memória dispensa o Redis.
ASGI_APPLICATION = "maestro.asgi.application"
CHANNELS_REDIS_URL = os.getenv(
    "CHANNELS_REDIS_URL", "redis://localhost:6379/1"
)
# O redis-py 8 passou a usar 5 s de tempo limite de leitura por padrão, e
# o channels_redis espera por mensagens com BZPOPMIN de até 5 s: a leitura
# estourava no limite e derrubava as conexões com "Timeout reading from".
# O tempo limite da leitura precisa ser maior que essa espera.
CHANNELS_REDIS_SOCKET_TIMEOUT = 30
CHANNEL_LAYERS = {
    "default": (
        {"BACKEND": "channels.layers.InMemoryChannelLayer"}
        if EXECUTANDO_TESTES
        else {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [
                    {
                        "address": CHANNELS_REDIS_URL,
                        "socket_timeout": CHANNELS_REDIS_SOCKET_TIMEOUT,
                    }
                ]
            },
        }
    )
}
