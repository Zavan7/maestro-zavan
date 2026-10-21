"""Serviços de cadastro de agentes, com auditoria.

Criar um agente, trocar o token e desativar ou reativar ficam aqui,
fora das views, no mesmo padrão da gestão de usuários: cada alteração é
gravada junto com um ``RegistroAcesso``, dentro da mesma transação. Um
token de agente é uma credencial; quem o gerou e quando fica registrado.

English:
    Agent registration services, with auditing.

    Creating an agent, changing the token and deactivating or
    reactivating live here, away from the views, following the user
    management pattern: each change is saved together with a
    ``RegistroAcesso``, inside the same transaction. An agent token is a
    credential; who generated it and when is recorded.
"""

from django.contrib.auth.models import User
from django.db import transaction

from agents.comandos import desconectar
from agents.models import Agente
from config.models import RegistroAcesso


def _registrar(autor: User, detalhe: str) -> None:
    """Grava a alteração de agente no registro de acesso.

    Args:
        autor: usuário que fez a alteração.
        detalhe: o que mudou, como ``maquina-01: criado``.

    English:
        Records the agent change in the access log.

        Args:
            autor: user who made the change.
            detalhe: what changed, such as ``maquina-01: criado``.
    """
    RegistroAcesso.objects.create(
        autor=autor, acao=RegistroAcesso.Acao.AGENTE, detalhe=detalhe
    )


@transaction.atomic
def criar_agente(autor: User, nome: str) -> tuple[Agente, str]:
    """Cria um agente ativo e devolve o token, que não é guardado.

    Args:
        autor: usuário que está criando o agente.
        nome: nome do agente, único.

    Returns:
        O agente criado e o token em texto, para ser mostrado uma vez.

    English:
        Creates an active agent and returns the token, which is not
        stored.

        Args:
            autor: user creating the agent.
            nome: agent name, unique.

        Returns:
            The created agent and the plain token, to be shown once.
    """
    agente = Agente(nome=nome, criado_por=autor)
    token = agente.novo_token()
    agente.save()
    _registrar(autor, f"{agente.nome}: criado")
    return agente, token


@transaction.atomic
def gerar_novo_token(autor: User, agente: Agente) -> str:
    """Troca o token do agente e derruba a conexão com o token antigo.

    Serve quando o token vazou ou a máquina foi trocada. O agente só
    volta a conectar com o token novo.

    Args:
        autor: usuário que pediu o token novo.
        agente: agente cujo token muda.

    Returns:
        O token novo em texto, para ser mostrado uma vez.

    English:
        Replaces the agent's token and drops the connection using the old
        one.

        Useful when the token leaked or the machine was replaced. The
        agent only reconnects with the new token.

        Args:
            autor: user who asked for the new token.
            agente: agent whose token changes.

        Returns:
            The new plain token, to be shown once.
    """
    token = agente.novo_token()
    agente.save(update_fields=["token_hash"])
    _registrar(autor, f"{agente.nome}: novo token")
    transaction.on_commit(lambda: desconectar(agente.pk))
    return token


@transaction.atomic
def alternar_agente(autor: User, agente: Agente) -> None:
    """Desativa um agente ativo ou reativa um desativado.

    Desativar derruba a conexão e impede o agente de conectar de novo,
    mas mantém o cadastro e o histórico dos robôs dele.

    Args:
        autor: usuário que fez a alteração.
        agente: agente a desativar ou reativar.

    English:
        Deactivates an active agent or reactivates a deactivated one.

        Deactivating drops the connection and stops the agent from
        connecting again, but keeps the record and its robots' history.

        Args:
            autor: user who made the change.
            agente: agent to deactivate or reactivate.
    """
    agente.ativo = not agente.ativo
    agente.save(update_fields=["ativo"])
    _registrar(
        autor,
        f"{agente.nome}: {'reativado' if agente.ativo else 'desativado'}",
    )
    if not agente.ativo:
        transaction.on_commit(lambda: desconectar(agente.pk))
