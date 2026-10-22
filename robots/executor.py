"""Executor de robôs: roda um processo, acompanha e encerra quando preciso.

Este módulo não conhece Django nem Celery. Ele recebe o comando e duas
funções: ``deve_parar`` (perguntada a cada segundo) e
``ao_receber_linha`` (chamada a cada linha da saída). Assim ele é
testável sem worker e sem banco, e define o mesmo contrato que o agente
em Go vai seguir: iniciar, acompanhar linha a linha, parar.

Por que uma thread para ler a saída? Ler ``stdout`` bloqueia até chegar
uma linha. Se o laço principal lesse direto, um robô calado por cinco
minutos travaria a conferência do tempo limite e do pedido de parada.
Com a thread, as linhas chegam por uma fila e o laço nunca espera mais
que uma fração de segundo.

Robôs de RPA costumam abrir processos filhos (navegador, chromedriver).
Por isso o robô roda num grupo de processos próprio
(``start_new_session=True``), e o encerramento atinge o grupo inteiro:
sem isso, os filhos ficariam vivos, segurando a saída aberta.

English:
    Robot executor: runs a process, watches it and stops it when needed.

    This module knows neither Django nor Celery. It takes the command
    and two functions: ``deve_parar`` (asked every second) and
    ``ao_receber_linha`` (called for each output line). That makes it
    testable without a worker or database, and it defines the same
    contract the Go agent will follow: start, watch line by line, stop.

    Why a thread to read the output? Reading ``stdout`` blocks until a
    line arrives. If the main loop read it directly, a robot silent for
    five minutes would stall the timeout and stop checks. With the
    thread, lines arrive through a queue and the loop never waits more
    than a fraction of a second.

    RPA robots often start child processes (browser, chromedriver). So
    the robot runs in its own process group (``start_new_session=True``),
    and stopping hits the whole group: otherwise the children would stay
    alive, holding the output open.
"""

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from typing import IO

PAUSA_LEITURA_SEGUNDOS = 0.1
INTERVALO_VERIFICACAO_SEGUNDOS = 1.0
ESPERA_ENCERRAMENTO_SEGUNDOS = 5.0


class Motivo(Enum):
    """Por que a execução terminou.

    Os valores em texto são os mesmos que o agente em Go envia na
    mensagem ``fim``. Os três últimos nunca saem do executor; são
    decididos antes ou em volta dele (``robots.ambiente``):

    - ``SCRIPT_INVALIDO``: o script não existe ou está fora da pasta
      aprovada;
    - ``AMBIENTE_INVALIDO``: a ferramenta de dependências do robô (uv,
      poetry, pdm, pipenv) não está instalada na máquina;
    - ``PREPARO_FALHOU``: a instalação das dependências falhou ou passou
      do tempo.

    English:
        Why the execution ended.

        The text values are the same ones the Go agent sends in the
        ``fim`` message. The last three never come out of the executor;
        they are decided before or around it (``robots.ambiente``):

        - ``SCRIPT_INVALIDO``: the script is missing or outside the
          approved folder;
        - ``AMBIENTE_INVALIDO``: the robot's dependency tool (uv, poetry,
          pdm, pipenv) is not installed on the machine;
        - ``PREPARO_FALHOU``: installing the dependencies failed or ran
          out of time.
    """

    CONCLUIDO = "concluido"
    TEMPO_ESGOTADO = "tempo_esgotado"
    PARADO = "parado"
    SCRIPT_INVALIDO = "script_invalido"
    AMBIENTE_INVALIDO = "ambiente_invalido"
    PREPARO_FALHOU = "preparo_falhou"


@dataclass(frozen=True, slots=True)
class ResultadoExecucao:
    """Resultado de uma execução: o motivo do fim e o código de saída.

    English:
        Result of a run: why it ended and the exit code.
    """

    motivo: Motivo
    codigo_saida: int


def executar(
    comando: list[str],
    cwd: Path,
    timeout_segundos: float,
    deve_parar: Callable[[], bool],
    ao_receber_linha: Callable[[str], None],
    a_cada_volta: Callable[[], None] | None = None,
    env: dict[str, str] | None = None,
    intervalo_verificacao: float = INTERVALO_VERIFICACAO_SEGUNDOS,
    espera_encerramento: float = ESPERA_ENCERRAMENTO_SEGUNDOS,
) -> ResultadoExecucao:
    """Roda ``comando`` até terminar, estourar o tempo ou ser parado.

    A saída de erro é juntada à saída padrão (``stderr=STDOUT``), para as
    linhas chegarem na ordem em que o robô as escreveu. O comando é uma
    lista de argumentos e roda sem ``shell=True``.

    Args:
        comando: programa e argumentos, por exemplo
            ``[sys.executable, "robo.py"]``.
        cwd: pasta de onde o processo roda.
        timeout_segundos: tempo máximo antes de encerrar o processo.
        deve_parar: função perguntada a cada ``intervalo_verificacao``
            segundos; ``True`` encerra o processo.
        ao_receber_linha: função chamada com cada linha da saída, sem a
            quebra de linha.
        a_cada_volta: função opcional chamada a cada volta do laço (cerca
            de dez vezes por segundo), com ou sem linha nova; serve para
            despachar o que foi acumulado mesmo com o robô calado.
        env: variáveis de ambiente do processo; ``None`` herda as de
            quem chama.
        intervalo_verificacao: de quanto em quanto tempo ``deve_parar`` é
            perguntada.
        espera_encerramento: quanto esperar o processo sair depois do
            pedido educado (``terminate``) antes de forçar (``kill``).

    Returns:
        O motivo do fim e o código de saída do processo.

    Raises:
        OSError: se o processo não pode ser iniciado.

    English:
        Runs ``comando`` until it ends, times out or is stopped.

        Standard error is merged into standard output (``stderr=STDOUT``),
        so lines arrive in the order the robot wrote them. The command is
        an argument list and runs without ``shell=True``.

        Args:
            comando: program and arguments, e.g.
                ``[sys.executable, "robo.py"]``.
            cwd: folder the process runs from.
            timeout_segundos: maximum time before stopping the process.
            deve_parar: function asked every ``intervalo_verificacao``
                seconds; ``True`` stops the process.
            ao_receber_linha: function called with each output line,
                without the line break.
            a_cada_volta: optional function called on every loop turn
                (about ten times a second), with or without a new line;
                it lets accumulated output be flushed even while the robot
                is silent.
            env: process environment variables; ``None`` inherits the
                caller's.
            intervalo_verificacao: how often ``deve_parar`` is asked.
            espera_encerramento: how long to wait for the process to exit
                after the polite request (``terminate``) before forcing it
                (``kill``).

        Returns:
            Why it ended and the process exit code.

        Raises:
            OSError: if the process cannot be started.
    """
    processo = subprocess.Popen(
        comando,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        start_new_session=True,
    )
    assert processo.stdout is not None  # garantido por stdout=PIPE
    fila: Queue[str | None] = Queue()
    leitor = threading.Thread(
        target=_ler_saida, args=(processo.stdout, fila), daemon=True
    )
    leitor.start()

    inicio = time.monotonic()
    proxima_verificacao = inicio + intervalo_verificacao
    motivo = Motivo.CONCLUIDO
    prazo_da_leitura: float | None = None  # definido ao mandar encerrar

    while True:
        try:
            linha = fila.get(timeout=PAUSA_LEITURA_SEGUNDOS)
        except Empty:
            pass
        else:
            if linha is None:
                break
            ao_receber_linha(linha.rstrip("\r\n"))
        if a_cada_volta is not None:
            a_cada_volta()

        agora = time.monotonic()
        if prazo_da_leitura is not None:
            if agora > prazo_da_leitura:
                break
            continue

        if agora - inicio > timeout_segundos:
            motivo = Motivo.TEMPO_ESGOTADO
        elif agora >= proxima_verificacao:
            proxima_verificacao = agora + intervalo_verificacao
            if deve_parar():
                motivo = Motivo.PARADO
        if motivo is not Motivo.CONCLUIDO:
            _encerrar(processo, espera_encerramento)
            prazo_da_leitura = time.monotonic() + espera_encerramento

    leitor.join(timeout=espera_encerramento)
    # Filhos que sobraram depois de o robô terminar (um navegador que não
    # foi fechado, por exemplo) são encerrados junto.
    _sinalizar_grupo(processo, signal.SIGKILL)
    return ResultadoExecucao(motivo, processo.wait())


def _ler_saida(saida: IO[str], fila: Queue[str | None]) -> None:
    """Lê a saída linha a linha e coloca cada uma na fila.

    Roda numa thread separada. Quando a saída fecha (o processo terminou
    ou foi encerrado), coloca ``None`` na fila para avisar o laço
    principal de que não vem mais nada.

    Args:
        saida: saída do processo, aberta em modo texto.
        fila: fila onde as linhas são entregues.

    English:
        Reads the output line by line and puts each one in the queue.

        It runs in a separate thread. When the output closes (the process
        ended or was stopped), it puts ``None`` in the queue to tell the
        main loop nothing else is coming.

        Args:
            saida: process output, opened in text mode.
            fila: queue where the lines are delivered.
    """
    for linha in saida:
        fila.put(linha)
    saida.close()
    fila.put(None)


def _encerrar(processo: subprocess.Popen[str], espera: float) -> None:
    """Pede para o grupo do processo sair e, se não obedecer, força.

    SIGTERM é o pedido educado, que o robô pode tratar para fechar
    arquivos e navegadores. Se ele não sair em ``espera`` segundos,
    SIGKILL encerra à força, sem poder ser ignorado. Os dois vão para o
    grupo inteiro (``killpg``), alcançando os processos filhos.

    Args:
        processo: processo a encerrar.
        espera: segundos de tolerância entre o pedido e a força.

    English:
        Asks the process to exit and, if it does not comply, forces it.

        SIGTERM is the polite request, which the robot may handle to
        close files and browsers. If it does not exit within ``espera``
        seconds, SIGKILL forces it, and cannot be ignored. Both go to the
        whole group (``killpg``), reaching the child processes.

        Args:
            processo: process to stop.
            espera: seconds of tolerance between the request and the
                force.
    """
    _sinalizar_grupo(processo, signal.SIGTERM)
    try:
        processo.wait(timeout=espera)
    except subprocess.TimeoutExpired:
        pass
    # Mesmo que o principal tenha saído, um filho pode ter ignorado o
    # SIGTERM; o SIGKILL no grupo garante que não sobra ninguém.
    _sinalizar_grupo(processo, signal.SIGKILL)


def _sinalizar_grupo(
    processo: subprocess.Popen[str], sinal: signal.Signals
) -> None:
    """Envia ``sinal`` ao grupo de processos do robô.

    Se o grupo já não existe (todos saíram), não há o que fazer.

    Args:
        processo: processo líder do grupo.
        sinal: sinal a enviar.

    English:
        Sends ``sinal`` to the robot's process group.

        If the group no longer exists (everyone exited), there is nothing
        to do.

        Args:
            processo: group leader process.
            sinal: signal to send.
    """
    try:
        os.killpg(processo.pid, sinal)
    except ProcessLookupError:
        pass
