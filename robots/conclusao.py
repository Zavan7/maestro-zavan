"""Como uma execução termina: status final, aviso à tela e nova tentativa.

As regras valem igual para quem rodou o robô, seja o worker do Celery
ou um agente: os dois informam só o motivo do fim e o código de saída,
e quem decide o status é o Maestro. Assim, a regra de "o que conta como
falha" e "quando tentar de novo" fica escrita uma vez só.

English:
    How an execution ends: final status, page notice and new attempt.

    The rules apply equally to whoever ran the robot, whether the Celery
    worker or an agent: both report only why it ended and the exit code,
    and Maestro decides the status. That way the rule of "what counts as
    a failure" and "when to try again" is written only once.
"""

import logging
from dataclasses import dataclass

from django.utils import timezone

from executions.ao_vivo import publicar_fim
from executions.models import Execucao
from robots.executor import Motivo

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Desfecho:
    """O status final de uma execução e o que fazer depois.

    English:
        An execution's final status and what to do next.
    """

    status: Execucao.Status
    pode_repetir: bool
    aviso: str | None = None


def desfecho(
    motivo: Motivo, codigo_saida: int | None, timeout_segundos: int
) -> Desfecho:
    """Traduz o motivo do fim e o código de saída no status final.

    - concluído com código 0: ``SUCESSO``;
    - concluído com outro código, ou tempo esgotado: ``FALHA``, que pode
      ter nova tentativa;
    - parado pelo usuário: ``CANCELADA``, sem nova tentativa;
    - script inválido ou ambiente inválido (a ferramenta de dependências
      não está instalada): ``FALHA`` sem nova tentativa, porque repetir
      não resolve um erro de configuração;
    - preparo que falhou: ``FALHA``, que pode ter nova tentativa, porque
      costuma ser rede.

    Args:
        motivo: por que a execução terminou.
        codigo_saida: código de saída do processo, se ele chegou a rodar.
        timeout_segundos: tempo limite usado, para a mensagem de aviso.

    Returns:
        O status, se pode haver nova tentativa e um aviso para o log.

    English:
        Turns the end reason and the exit code into the final status.

        - finished with code 0: ``SUCESSO``;
        - finished with another code, or timed out: ``FALHA``, which may
          get a new attempt;
        - stopped by the user: ``CANCELADA``, with no new attempt;
        - invalid script or invalid environment (the dependency tool is
          not installed): ``FALHA`` with no new attempt, because
          repeating does not fix a configuration error;
        - failed preparation: ``FALHA``, which may get a new attempt,
          because it is usually the network.

        Args:
            motivo: why the execution ended.
            codigo_saida: process exit code, if it got to run.
            timeout_segundos: timeout used, for the warning message.

        Returns:
            The status, whether a new attempt may happen and a warning for
            the log.
    """
    match motivo:
        case Motivo.PARADO:
            return Desfecho(
                Execucao.Status.CANCELADA,
                pode_repetir=False,
                aviso="Execução parada pelo usuário.",
            )
        case Motivo.TEMPO_ESGOTADO:
            return Desfecho(
                Execucao.Status.FALHA,
                pode_repetir=True,
                aviso=f"Execução excedeu o limite de {timeout_segundos}s.",
            )
        case Motivo.SCRIPT_INVALIDO | Motivo.AMBIENTE_INVALIDO:
            return Desfecho(Execucao.Status.FALHA, pode_repetir=False)
        case Motivo.CONCLUIDO if codigo_saida == 0:
            return Desfecho(Execucao.Status.SUCESSO, pode_repetir=False)
        case _:
            return Desfecho(Execucao.Status.FALHA, pode_repetir=True)


def finalizar_execucao(execucao: Execucao, fim: Desfecho) -> None:
    """Grava o status final, avisa a tela e, se for o caso, tenta de novo.

    O log e ``total_linhas`` já devem estar na instância; são gravados
    junto com o status. O aviso à tela sai depois da gravação, porque o
    navegador recarrega a página ao recebê-lo.

    Args:
        execucao: execução que terminou, com o log final preenchido.
        fim: desfecho calculado por ``desfecho``.

    English:
        Saves the final status, notifies the page and, if needed, tries
        again.

        The log and ``total_linhas`` must already be on the instance; they
        are saved together with the status. The page notice goes out after
        saving, because the browser reloads the page when it gets it.

        Args:
            execucao: execution that ended, with the final log filled in.
            fim: outcome computed by ``desfecho``.
    """
    execucao.status = fim.status
    execucao.finalizado_em = timezone.now()
    execucao.save(
        update_fields=["log", "total_linhas", "status", "finalizado_em"]
    )
    publicar_fim(execucao.pk, fim.status)

    if fim.pode_repetir:
        tentar_de_novo(execucao)


def tentar_de_novo(execucao: Execucao) -> None:
    """Dispara a próxima tentativa, se o robô ainda tiver alguma.

    ``max_tentativas`` conta as tentativas extras: com 2, um robô roda no
    máximo 3 vezes. Cada tentativa é uma ``Execucao`` nova, com log e
    duração próprios, disparada pelo mesmo serviço do botão; se ele
    recusar (o robô foi para manutenção ou o agente saiu do ar, por
    exemplo), só fica um aviso no log.

    O import de ``robots.services`` fica dentro da função porque o
    serviço importa a tarefa do worker, que importa este módulo; no topo,
    os módulos dependeriam um do outro ao carregar.

    Args:
        execucao: execução que acabou de falhar.

    English:
        Triggers the next attempt, if the robot has any left.

        ``max_tentativas`` counts the extra attempts: with 2, a robot runs
        at most 3 times. Each attempt is a new ``Execucao``, with its own
        log and duration, triggered by the same service as the button; if
        it refuses (the robot went into maintenance or the agent went
        offline, for example), only a warning is logged.

        The ``robots.services`` import lives inside the function because
        the service imports the worker task, which imports this module; at
        the top, the modules would depend on each other while loading.

        Args:
            execucao: execution that has just failed.
    """
    from robots.services import DisparoRecusado, disparar_execucao

    if execucao.tentativa > execucao.robo.max_tentativas:
        return
    try:
        disparar_execucao(
            execucao.robo,
            disparado_por=execucao.disparado_por,
            origem=Execucao.Origem(execucao.origem),
            agendamento=execucao.agendamento,
            tentativa=execucao.tentativa + 1,
        )
    except DisparoRecusado as erro:
        logger.warning(
            "Nova tentativa de %s não disparou: %s", execucao.robo, erro
        )
