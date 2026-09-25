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
    base = Path(settings.ROBOS_SCRIPTS_DIR).resolve()
    script = (base / caminho).resolve()

    if not script.is_relative_to(base):
        raise ValueError("Script fora do diretório permitido.")
    if not script.is_file():
        raise FileNotFoundError(f"Script não encontrado: {caminho}")

    return script


@shared_task
def executar_robo(execucao_id):
    execucao = Execucao.objects.select_related("robo").get(pk=execucao_id)
    execucao.status = Execucao.Status.RODANDO
    execucao.iniciado_em = timezone.now()
    execucao.save(update_fields=["status", "iniciado_em"])

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
            Execucao.Status.SUCESSO if resultado.returncode == 0 else Execucao.Status.FALHA
        )
    except subprocess.TimeoutExpired:
        execucao.log = f"Execução excedeu o limite de {TIMEOUT_SEGUNDOS}s."
        execucao.status = Execucao.Status.FALHA
    except (ValueError, FileNotFoundError) as erro:
        execucao.log = str(erro)
        execucao.status = Execucao.Status.FALHA

    execucao.finalizado_em = timezone.now()
    execucao.save(update_fields=["log", "status", "finalizado_em"])