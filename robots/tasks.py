"""Tarefas Celery do app de robôs.

Estas funções rodam no worker do Celery, fora do servidor web. Por
isso elas recebem só o ``id`` da execução, e não o objeto: o worker
busca o registro atualizado no banco.

Rodar o processo em si (tempo limite, parada, leitura da saída) é papel
de ``robots.executor``; aqui fica o que depende do banco: reivindicar a
execução, o status final, o log e a nova tentativa.

English:
    Celery tasks for the robots app.

    These functions run in the Celery worker, outside the web server.
    That is why they receive only the execution ``id``, not the object:
    the worker fetches the up-to-date record from the database.

    Running the process itself (timeout, stopping, reading the output)
    is the job of ``robots.executor``; here lives what depends on the
    database: claiming the execution, the final status, the log and the
    new attempt.
"""

import sys
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from config.models import ConfiguracaoSistema
from executions.ao_vivo import LinhaDoLog, publicar_linhas
from executions.models import Execucao
from robots.conclusao import desfecho, finalizar_execucao
from robots.executor import Motivo, executar

INTERVALO_DESPACHO_SEGUNDOS = 0.5


class LogLimitado:
    """Acumula as linhas do log guardando só os últimos caracteres.

    O fim do log é onde ficam os erros, então, passado o limite, as
    linhas mais antigas são descartadas. Um ``deque`` remove do começo
    sem copiar a lista inteira.

    English:
        Accumulates log lines, keeping only the last characters.

        The end of the log is where the errors are, so past the limit
        the oldest lines are dropped. A ``deque`` removes from the start
        without copying the whole list.
    """

    def __init__(self, limite: int) -> None:
        """Cria o log vazio com o limite de caracteres.

        Args:
            limite: quantos caracteres do fim do log guardar.

        English:
            Creates the empty log with the character limit.

            Args:
                limite: how many characters from the end of the log to
                    keep.
        """
        self.limite = limite
        self.linhas: deque[str] = deque()
        self.tamanho = 0

    def adicionar(self, linha: str) -> None:
        """Acrescenta uma linha e descarta as mais antigas além do limite.

        Args:
            linha: linha do log, sem a quebra de linha.

        English:
            Appends a line and drops the oldest ones past the limit.

            Args:
                linha: log line, without the line break.
        """
        self.linhas.append(linha)
        self.tamanho += len(linha) + 1
        while self.tamanho > self.limite and len(self.linhas) > 1:
            self.tamanho -= len(self.linhas.popleft()) + 1

    def texto(self) -> str:
        """Retorna o log como texto, cortado no limite de caracteres.

        Returns:
            As linhas guardadas, uma por linha.

        English:
            Returns the log as text, cut at the character limit.

            Returns:
                The stored lines, one per line.
        """
        return "\n".join(self.linhas)[-self.limite :]


class LogAoVivo:
    """Log da execução que vai para a tela enquanto o robô roda.

    Cada linha ganha um número desde o início da execução e entra num
    ``LogLimitado``. Em vez de mandar linha a linha, o log junta as
    linhas e, a cada ``INTERVALO_DESPACHO_SEGUNDOS``, grava no banco e só
    então envia o lote à tela. Os lotes limitam um robô muito falante a
    poucas escritas e mensagens por segundo.

    Por que gravar antes de enviar? Assim, toda linha que já foi enviada
    também está no banco. O consumer, ao conectar, entra no grupo e só
    depois lê o log do banco: o que já foi gravado vem nessa leitura, e o
    que ainda não foi será enviado com ele já no grupo. Nenhuma linha se
    perde entre abrir a página e o WebSocket conectar. O ``relogio`` pode
    ser trocado nos testes.

    English:
        Execution log that reaches the page while the robot runs.

        Each line gets a number since the start of the execution and goes
        into a ``LogLimitado``. Instead of sending line by line, the log
        gathers lines and, every ``INTERVALO_DESPACHO_SEGUNDOS``, saves to
        the database and only then sends the batch to the page. Batches
        cap a very chatty robot at a few writes and messages per second.

        Why save before sending? That way, every line already sent is
        also in the database. On connect, the consumer joins the group and
        only then reads the log from the database: what was already saved
        comes in that read, and what was not will be sent with it already
        in the group. No line is lost between opening the page and the
        WebSocket connecting. The ``relogio`` can be swapped in tests.
    """

    def __init__(
        self,
        execucao_id: int,
        limite: int,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        """Cria o log vazio de uma execução.

        Args:
            execucao_id: id da execução cujo log é este.
            limite: quantos caracteres do fim do log guardar.
            relogio: função que devolve o tempo em segundos.

        English:
            Creates the empty log of an execution.

            Args:
                execucao_id: id of the execution this log belongs to.
                limite: how many characters from the end of the log to
                    keep.
                relogio: function that returns the time in seconds.
        """
        self.execucao_id = execucao_id
        self.guardado = LogLimitado(limite)
        self.relogio = relogio
        self.total_linhas = 0
        self.pendentes: list[LinhaDoLog] = []
        self.ultimo_despacho = float("-inf")

    def adicionar(self, linha: str) -> None:
        """Numera e guarda uma linha, e despacha o lote se for a hora.

        A primeira linha sai na hora (``ultimo_despacho`` começa em menos
        infinito), para a tela não ficar parada no começo.

        Args:
            linha: linha do log, sem a quebra de linha.

        English:
            Numbers and stores a line, and flushes the batch if it is time.

            The first line goes out right away (``ultimo_despacho`` starts
            at minus infinity), so the page is not idle at the start.

            Args:
                linha: log line, without the line break.
        """
        self.total_linhas += 1
        self.guardado.adicionar(linha)
        self.pendentes.append(
            LinhaDoLog(numero=self.total_linhas, texto=linha)
        )
        self.despachar()

    def despachar(self) -> None:
        """Grava e envia o lote acumulado, se o intervalo já passou.

        O executor chama este método a cada volta do laço, então o lote
        sai no tempo certo mesmo que o robô fique calado.

        English:
            Saves and sends the accumulated batch, if the interval passed.

            The executor calls this method on every loop turn, so the
            batch goes out on time even if the robot stays silent.
        """
        agora = self.relogio()
        if self.pendentes and (
            agora - self.ultimo_despacho >= INTERVALO_DESPACHO_SEGUNDOS
        ):
            self._gravar_e_enviar()
            self.ultimo_despacho = agora

    def encerrar(self) -> None:
        """Grava e envia as últimas linhas, sem esperar o intervalo.

        English:
            Saves and sends the last lines, without waiting for the
            interval.
        """
        if self.pendentes:
            self._gravar_e_enviar()

    def texto(self) -> str:
        """Retorna o log guardado, cortado no limite de caracteres.

        Returns:
            As linhas guardadas, uma por linha.

        English:
            Returns the stored log, cut at the character limit.

            Returns:
                The stored lines, one per line.
        """
        return self.guardado.texto()

    def _gravar_e_enviar(self) -> None:
        """Grava o log no banco e, em seguida, envia o lote à tela.

        English:
            Saves the log to the database and then sends the batch to the
            page.
        """
        Execucao.objects.filter(pk=self.execucao_id).update(
            log=self.texto(), total_linhas=self.total_linhas
        )
        publicar_linhas(self.execucao_id, self.pendentes)
        self.pendentes = []


def _resolver_script(caminho: str) -> Path:
    """Resolve o caminho do script com segurança dentro da pasta permitida.

    ``resolve()`` transforma o caminho em absoluto e resolve ``..`` e
    links simbólicos. Depois, ``is_relative_to(base)`` confere que o
    resultado continua dentro de ``ROBOS_SCRIPTS_DIR``. Isso impede que um
    cadastro como ``../../etc/script.py`` execute algo fora da pasta.

    Args:
        caminho: caminho do script, relativo à pasta de scripts.

    Returns:
        Caminho absoluto do script.

    Raises:
        ValueError: se o caminho sai da pasta permitida.
        FileNotFoundError: se o script não existe.

    English:
        Safely resolves the script path inside the allowed folder.

        ``resolve()`` makes the path absolute and resolves ``..`` and
        symlinks. Then ``is_relative_to(base)`` checks that the result is
        still inside ``ROBOS_SCRIPTS_DIR``. This stops an entry such as
        ``../../etc/script.py`` from running something outside the folder.

        Args:
            caminho: script path, relative to the scripts folder.

        Returns:
            Absolute path to the script.

        Raises:
            ValueError: if the path leaves the allowed folder.
            FileNotFoundError: if the script does not exist.
    """
    base = Path(settings.ROBOS_SCRIPTS_DIR).resolve()
    script = (base / caminho).resolve()

    if not script.is_relative_to(base):
        raise ValueError("Script fora do diretório permitido.")
    if not script.is_file():
        raise FileNotFoundError(f"Script não encontrado: {caminho}")

    return script


@shared_task
def executar_robo(execucao_id: int) -> None:
    """Roda o script do robô e grava o resultado na execução.

    Fluxo:

    1. Reivindica a execução: um ``UPDATE`` condicional troca
       ``PENDENTE`` por ``RODANDO`` e anota o início. Se nada foi
       atualizado, a execução já não está pendente (foi cancelada pelo
       botão "parar" antes de o worker chegar nela, ou a tarefa chegou
       duas vezes) e a tarefa termina sem rodar o script.
    2. Roda o script pelo executor, com o Python do Maestro
       (``sys.executable``) em modo sem buffer (``-u``), para cada linha
       chegar assim que o robô a escreve. O tempo limite é o do robô ou,
       se ele não define, o padrão da aba de configurações.
    3. A cada segundo o executor pergunta se ``parada_solicitada`` foi
       marcada pelo botão "parar". Enquanto isso, as linhas vão para o
       banco e para a tela ao vivo em lotes (``LogAoVivo``).
    4. Grava status e log: saída 0 vira ``SUCESSO``; outro código ou
       tempo esgotado, ``FALHA``; parada pedida, ``CANCELADA``. Caminho
       inválido ou script inexistente também viram ``FALHA``. Depois de
       gravar, avisa a tela que a execução terminou (``publicar_fim``).
    5. Se falhou e o robô ainda tem tentativas, dispara a próxima. As
       regras dos passos 4 e 5 ficam em ``robots.conclusao``, as mesmas
       para o worker e para o agente.

    Args:
        execucao_id: id da ``Execucao`` pendente a ser processada.

    English:
        Runs the robot's script and saves the result on the execution.

        Flow:

        1. Claims the execution: a conditional ``UPDATE`` swaps
           ``PENDENTE`` for ``RODANDO`` and records the start time. If
           nothing was updated, the execution is no longer pending (it
           was cancelled with the "stop" button before the worker got to
           it, or the task arrived twice) and the task ends without
           running the script.
        2. Runs the script through the executor, with Maestro's Python
           (``sys.executable``) in unbuffered mode (``-u``), so each line
           arrives as soon as the robot writes it. The timeout is the
           robot's own or, if it sets none, the settings tab default.
        3. Every second the executor asks whether ``parada_solicitada``
           was set by the "stop" button. Meanwhile, the lines go to the
           database and to the page live in batches (``LogAoVivo``).
        4. Saves status and log: exit 0 becomes ``SUCESSO``; another code
           or a timeout, ``FALHA``; a stop request, ``CANCELADA``. An
           invalid path or missing script also become ``FALHA``. After
           saving, tells the page the execution has ended
           (``publicar_fim``).
        5. If it failed and the robot still has attempts left, triggers
           the next one. The rules of steps 4 and 5 live in
           ``robots.conclusao``, the same for the worker and the agent.

        Args:
            execucao_id: id of the pending ``Execucao`` to process.
    """
    reivindicada = Execucao.objects.filter(
        pk=execucao_id, status=Execucao.Status.PENDENTE
    ).update(status=Execucao.Status.RODANDO, iniciado_em=timezone.now())
    if not reivindicada:
        return

    execucao = Execucao.objects.select_related("robo").get(pk=execucao_id)
    configuracao = ConfiguracaoSistema.atual()
    timeout = (
        execucao.robo.timeout_segundos or configuracao.timeout_padrao_segundos
    )
    log = LogAoVivo(execucao_id, configuracao.limite_log)

    try:
        script = _resolver_script(execucao.robo.caminho_script)
        resultado = executar(
            [sys.executable, "-u", str(script)],
            cwd=script.parent,
            timeout_segundos=timeout,
            deve_parar=lambda: _parada_solicitada(execucao_id),
            ao_receber_linha=log.adicionar,
            a_cada_volta=log.despachar,
        )
        motivo, codigo_saida = resultado.motivo, resultado.codigo_saida
    except (ValueError, FileNotFoundError) as erro:
        log.adicionar(str(erro))
        motivo, codigo_saida = Motivo.SCRIPT_INVALIDO, None

    fim = desfecho(motivo, codigo_saida, timeout)
    if fim.aviso:
        log.adicionar(fim.aviso)
    log.encerrar()
    execucao.log = log.texto()
    execucao.total_linhas = log.total_linhas
    finalizar_execucao(execucao, fim)


def _parada_solicitada(execucao_id: int) -> bool:
    """Indica se o botão "parar" foi usado para esta execução.

    Args:
        execucao_id: id da execução em andamento.

    Returns:
        ``True`` se ``parada_solicitada`` foi marcada.

    English:
        Tells whether the "stop" button was used for this execution.

        Args:
            execucao_id: id of the running execution.

        Returns:
            ``True`` if ``parada_solicitada`` was set.
    """
    return Execucao.objects.filter(
        pk=execucao_id, parada_solicitada=True
    ).exists()
