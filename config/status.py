"""Verificações do status do sistema: Redis, worker e agendador.

Cada verificação devolve um ``ItemStatus`` pronto para a tela, e nenhuma
levanta exceção: um serviço fora do ar é uma resposta válida, não um
erro da página.

Como saber se o agendador (``celery beat``) está vivo? Ele não responde a
``ping``. Por isso, a cada minuto ele envia a tarefa
``registrar_pulso_agendador``, que grava a hora atual no Redis com
validade curta. Se a chave sumiu ou está velha, o agendador (ou o worker
que executa a tarefa) parou.

English:
    System status checks: Redis, worker and scheduler.

    Each check returns an ``ItemStatus`` ready for the page, and none of
    them raises: a service being down is a valid answer, not a page error.

    How do we know the scheduler (``celery beat``) is alive? It does not
    answer ``ping``. So, every minute it sends the
    ``registrar_pulso_agendador`` task, which writes the current time to
    Redis with a short expiry. If the key is gone or stale, the scheduler
    (or the worker running the task) has stopped.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import redis
from django.conf import settings
from django.utils import timezone
from kombu.exceptions import OperationalError

from agents.models import Agente
from maestro.celery import app

CHAVE_PULSO_AGENDADOR = "maestro:agendador:pulso"
VALIDADE_PULSO_SEGUNDOS = 180
TIMEOUT_VERIFICACAO_SEGUNDOS = 1.0


class ClienteRedis(Protocol):
    """O pedaço do cliente do Redis que as verificações usam.

    Um ``Protocol`` descreve um formato, não uma herança: qualquer objeto
    com esses três métodos serve, seja o ``redis.Redis`` real ou um
    substituto em memória nos testes.

    English:
        The part of the Redis client that the checks use.

        A ``Protocol`` describes a shape, not inheritance: any object with
        these three methods fits, whether the real ``redis.Redis`` or an
        in-memory stand-in in tests.
    """

    def ping(self) -> object:
        """Confere se o Redis responde.

        English:
            Checks whether Redis answers.
        """

    def get(self, name: str) -> object:
        """Lê o valor de uma chave.

        English:
            Reads a key's value.
        """

    def set(self, name: str, value: str, ex: int | None = None) -> object:
        """Grava o valor de uma chave, com validade opcional em segundos.

        English:
            Writes a key's value, with an optional expiry in seconds.
        """


@dataclass(frozen=True, slots=True)
class ItemStatus:
    """Resultado de uma verificação, no formato que a tela exibe.

    English:
        Result of one check, in the format the page shows.
    """

    nome: str
    ok: bool
    detalhe: str


def conectar_redis() -> redis.Redis:
    """Cria um cliente do Redis do broker com tempo limite curto.

    O tempo limite evita que a aba de configurações fique travada
    esperando um Redis que não responde.

    Returns:
        Cliente do Redis apontando para ``CELERY_BROKER_URL``.

    English:
        Creates a client for the broker's Redis with a short timeout.

        The timeout keeps the settings tab from hanging while waiting for a
        Redis that does not answer.

        Returns:
            Redis client pointing to ``CELERY_BROKER_URL``.
    """
    return redis.Redis.from_url(
        settings.CELERY_BROKER_URL,
        socket_timeout=TIMEOUT_VERIFICACAO_SEGUNDOS,
        socket_connect_timeout=TIMEOUT_VERIFICACAO_SEGUNDOS,
    )


def verificar_redis(cliente: ClienteRedis) -> ItemStatus:
    """Verifica se o Redis responde ao ``PING``.

    Args:
        cliente: cliente do Redis a verificar.

    Returns:
        O status do Redis.

    English:
        Checks whether Redis answers ``PING``.

        Args:
            cliente: Redis client to check.

        Returns:
            The Redis status.
    """
    try:
        cliente.ping()
    except redis.RedisError:
        return ItemStatus("fila (Redis)", False, "sem resposta")
    return ItemStatus("fila (Redis)", True, "respondendo")


def verificar_worker() -> ItemStatus:
    """Verifica se algum worker do Celery responde ao ``ping``.

    ``inspect().ping()`` devolve um dicionário com um item por worker que
    respondeu dentro do tempo limite, ou ``None`` se nenhum respondeu.

    Returns:
        O status do worker, com a quantidade de workers ativos.

    English:
        Checks whether any Celery worker answers ``ping``.

        ``inspect().ping()`` returns a dict with one item per worker that
        answered within the timeout, or ``None`` if none did.

        Returns:
            The worker status, with the number of active workers.
    """
    try:
        respostas = app.control.inspect(
            timeout=TIMEOUT_VERIFICACAO_SEGUNDOS
        ).ping()
    except OSError, OperationalError:
        respostas = None

    if not respostas:
        return ItemStatus("worker", False, "nenhum worker respondeu")
    quantidade = len(respostas)
    sufixo = "" if quantidade == 1 else "s"
    return ItemStatus("worker", True, f"{quantidade} ativo{sufixo}")


def verificar_agendador(
    cliente: ClienteRedis, agora: datetime | None = None
) -> ItemStatus:
    """Verifica se o agendador gravou um pulso recente no Redis.

    Args:
        cliente: cliente do Redis onde o pulso é gravado.
        agora: momento de referência; ``None`` usa a hora atual.

    Returns:
        O status do agendador, com a idade do último pulso.

    English:
        Checks whether the scheduler wrote a recent pulse to Redis.

        Args:
            cliente: Redis client where the pulse is written.
            agora: reference moment; ``None`` uses the current time.

        Returns:
            The scheduler status, with the age of the last pulse.
    """
    agora = agora or timezone.now()
    try:
        valor = cliente.get(CHAVE_PULSO_AGENDADOR)
    except redis.RedisError:
        return ItemStatus("agendador", False, "sem conexão com o Redis")

    if valor is None:
        return ItemStatus("agendador", False, "nenhum sinal recente")

    ultimo_pulso = datetime.fromisoformat(_como_texto(valor))
    idade = int((agora - ultimo_pulso).total_seconds())
    if idade > VALIDADE_PULSO_SEGUNDOS:
        return ItemStatus("agendador", False, f"último sinal há {idade}s")
    return ItemStatus("agendador", True, f"último sinal há {idade}s")


def _como_texto(valor: object) -> str:
    """Converte o valor lido do Redis em texto.

    O cliente do Redis devolve ``bytes`` por padrão.

    Args:
        valor: valor lido do Redis.

    Returns:
        O valor como ``str``.

    English:
        Converts the value read from Redis to text.

        The Redis client returns ``bytes`` by default.

        Args:
            valor: value read from Redis.

        Returns:
            The value as ``str``.
    """
    return valor.decode() if isinstance(valor, bytes) else str(valor)


def registrar_pulso(
    cliente: ClienteRedis | None = None, agora: datetime | None = None
) -> None:
    """Grava no Redis a hora do pulso do agendador, com validade curta.

    A validade (``ex``) faz a chave sumir sozinha se o agendador parar,
    então uma chave ausente já significa "parado".

    Args:
        cliente: cliente do Redis; ``None`` cria um novo.
        agora: hora do pulso; ``None`` usa a hora atual.

    English:
        Writes the scheduler pulse time to Redis, with a short expiry.

        The expiry (``ex``) makes the key vanish on its own if the
        scheduler stops, so a missing key already means "stopped".

        Args:
            cliente: Redis client; ``None`` creates a new one.
            agora: pulse time; ``None`` uses the current time.
    """
    cliente = cliente or conectar_redis()
    agora = agora or timezone.now()
    cliente.set(
        CHAVE_PULSO_AGENDADOR, agora.isoformat(), ex=VALIDADE_PULSO_SEGUNDOS
    )


def verificar_agentes() -> ItemStatus:
    """Conta quantos agentes ativos estão online.

    Fica ok quando todos os agentes ativos estão online, ou quando não
    há nenhum (todos os robôs rodam no worker).

    Returns:
        O status dos agentes.

    English:
        Counts how many active agents are online.

        It is ok when every active agent is online, or when there is none
        (all robots run in the worker).

        Returns:
            The agents status.
    """
    ativos = list(Agente.objects.filter(ativo=True))
    if not ativos:
        return ItemStatus("agentes", True, "nenhum cadastrado")
    online = sum(agente.online() for agente in ativos)
    return ItemStatus(
        "agentes", online == len(ativos), f"{online} de {len(ativos)} online"
    )


def status_do_sistema() -> list[ItemStatus]:
    """Verifica Redis, worker, agendador e agentes, nessa ordem.

    Worker e agendador dependem do Redis. Se ele não responde, os dois
    são marcados como parados sem nova tentativa, para a página não
    esperar o tempo limite de cada um.

    Returns:
        Os quatro status, prontos para a tela.

    English:
        Checks Redis, worker, scheduler and agents, in that order.

        Worker and scheduler depend on Redis. If it does not answer, both
        are marked as stopped without another attempt, so the page does
        not wait for each one's timeout.

        Returns:
            The four statuses, ready for the page.
    """
    cliente = conectar_redis()
    status_redis = verificar_redis(cliente)
    if not status_redis.ok:
        return [
            status_redis,
            ItemStatus("worker", False, "sem conexão com o Redis"),
            ItemStatus("agendador", False, "sem conexão com o Redis"),
            verificar_agentes(),
        ]
    return [
        status_redis,
        verificar_worker(),
        verificar_agendador(cliente),
        verificar_agentes(),
    ]
