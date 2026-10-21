"""Tarefas Celery do app de robôs.

Estas funções rodam no worker do Celery, fora do servidor web. Por
isso elas recebem só o ``id`` da execução, e não o objeto: o worker
busca o registro atualizado no banco.

English:
    Celery tasks for the robots app.

    These functions run in the Celery worker, outside the web server.
    That is why they receive only the execution ``id``, not the object:
    the worker fetches the up-to-date record from the database.
"""
import subprocess
import sys
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from executions.models import Execucao

LIMITE_LOG = 10_000
TIMEOUT_SEGUNDOS = 300


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
    2. Roda o script com o mesmo Python do Maestro (``sys.executable``),
       numa lista de argumentos e sem ``shell=True``, o que evita injeção
       de comandos.
    3. Guarda a saída (stdout + stderr), limitada aos últimos
       ``LIMITE_LOG`` caracteres para o banco não crescer demais.
    4. Código de saída 0 vira ``SUCESSO``; qualquer outro, ``FALHA``.
    5. Tempo esgotado, script inexistente ou caminho inválido também viram
       ``FALHA``, com a explicação no log.

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
        2. Runs the script with Maestro's own Python (``sys.executable``),
           as an argument list and without ``shell=True``, which prevents
           command injection.
        3. Stores the output (stdout + stderr), trimmed to the last
           ``LIMITE_LOG`` characters so the database does not grow too
           much.
        4. Exit code 0 becomes ``SUCESSO``; anything else, ``FALHA``.
        5. Timeout, missing script or invalid path also become ``FALHA``,
           with the explanation in the log.

        Args:
            execucao_id: id of the pending ``Execucao`` to process.
    """
    reivindicada = Execucao.objects.filter(
        pk=execucao_id, status=Execucao.Status.PENDENTE
    ).update(status=Execucao.Status.RODANDO, iniciado_em=timezone.now())
    if not reivindicada:
        return

    execucao = Execucao.objects.select_related("robo").get(pk=execucao_id)

    try:
        script = _resolver_script(execucao.robo.caminho_script)
        resultado = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEGUNDOS,
            cwd=script.parent,
        )
        execucao.log = (resultado.stdout + resultado.stderr)[-LIMITE_LOG:]
        execucao.status = (
            Execucao.Status.SUCESSO
            if resultado.returncode == 0
            else Execucao.Status.FALHA
        )
    except subprocess.TimeoutExpired:
        execucao.log = f"Execução excedeu o limite de {TIMEOUT_SEGUNDOS}s."
        execucao.status = Execucao.Status.FALHA
    except (ValueError, FileNotFoundError) as erro:
        execucao.log = str(erro)
        execucao.status = Execucao.Status.FALHA

    execucao.finalizado_em = timezone.now()
    execucao.save(update_fields=["log", "status", "finalizado_em"])
