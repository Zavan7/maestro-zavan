"""Ambiente de cada robô: qual gerenciador de dependências ele usa.

Cada robô pode ser um projeto com o próprio gerenciador: uv, poetry,
pdm, pipenv ou um ``requirements.txt`` com pip. Este módulo olha os
arquivos da pasta do robô, escolhe a ferramenta, prepara as dependências
e roda o robô dentro do ambiente dele. Não conhece Django nem Celery: o
worker usa este módulo, e o agente em Go segue a mesma regra
(``agente-go/internal/ambiente``), descrita em
``docs/agente/protocolo.md``.

A detecção olha só a pasta do script, nunca as pastas acima: um robô
avulso em ``scripts/`` acharia, subindo, o ``uv.lock`` do próprio
Maestro.

English:
    Each robot's environment: which dependency manager it uses.

    Each robot may be a project with its own manager: uv, poetry, pdm,
    pipenv or a ``requirements.txt`` with pip. This module looks at the
    files in the robot's folder, picks the tool, prepares the
    dependencies and runs the robot inside its environment. It knows
    neither Django nor Celery: the worker uses this module, and the Go
    agent follows the same rule (``agente-go/internal/ambiente``),
    described in ``docs/agente/protocolo.md``.

    Detection only looks at the script's folder, never the folders
    above: a standalone robot in ``scripts/`` would find, going up,
    Maestro's own ``uv.lock``.
"""

import os
import shutil
import sys
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from robots.executor import Motivo, executar

TEMPO_MAXIMO_PREPARO_SEGUNDOS = 900
PREFIXO = "[ambiente]"

# Variáveis de quem roda o robô que não podem vazar para ele: um venv
# ativo faria o uv, o poetry ou o pipenv instalarem as dependências do
# robô no ambiente do Maestro ou do agente, e o token é a credencial do
# agente.
VARIAVEIS_REMOVIDAS = (
    "VIRTUAL_ENV",
    "UV_PROJECT_ENVIRONMENT",
    "POETRY_ACTIVE",
    "PIPENV_ACTIVE",
    "PYTHONHOME",
    "PYTHONPATH",
    "MAESTRO_TOKEN",
)


class Ferramenta(StrEnum):
    """Gerenciador de dependências de um robô.

    English:
        A robot's dependency manager.
    """

    UV = "uv"
    POETRY = "poetry"
    PDM = "pdm"
    PIPENV = "pipenv"
    PIP = "pip"
    SISTEMA = "sistema"


# Arquivos que identificam a ferramenta sozinhos, em ordem de prioridade:
# um lock diz com certeza quem gerencia o projeto.
MARCADORES = (
    ("uv.lock", Ferramenta.UV),
    ("poetry.lock", Ferramenta.POETRY),
    ("pdm.lock", Ferramenta.PDM),
    ("Pipfile.lock", Ferramenta.PIPENV),
    ("Pipfile", Ferramenta.PIPENV),
)


@dataclass(frozen=True, slots=True)
class Programas:
    """Programas usados para cada ferramenta, por nome ou caminho.

    English:
        Programs used for each tool, by name or path.
    """

    uv: str = "uv"
    poetry: str = "poetry"
    pdm: str = "pdm"
    pipenv: str = "pipenv"
    python: str = sys.executable


@dataclass(frozen=True, slots=True)
class Plano:
    """Como preparar e rodar um robô.

    ``programa`` é o que precisa estar instalado (``None`` quando o
    próprio Python basta); ``preparo`` são os comandos que instalam as
    dependências; ``python`` é o começo do comando que roda Python dentro
    do ambiente do robô (``["poetry", "run", "python"]``, por exemplo).

    English:
        How to prepare and run a robot.

        ``programa`` is what must be installed (``None`` when Python
        itself is enough); ``preparo`` are the commands that install the
        dependencies; ``python`` is the start of the command that runs
        Python inside the robot's environment
        (``["poetry", "run", "python"]``, for example).
    """

    ferramenta: Ferramenta
    origem: str
    pasta: Path
    programa: str | None
    preparo: list[list[str]]
    python: list[str]
    env: dict[str, str] = field(default_factory=dict)

    def comando(self, script: Path) -> list[str]:
        """Monta o comando que roda o script sem buffer de saída.

        Args:
            script: caminho absoluto do script do robô.

        Returns:
            O comando, como lista de argumentos.

        English:
            Builds the command that runs the script without output
            buffering.

            Args:
                script: absolute path to the robot's script.

            Returns:
                The command, as an argument list.
        """
        return [*self.python, "-u", str(script)]


def detectar(pasta: Path) -> tuple[Ferramenta, str]:
    """Descobre o gerenciador de dependências pelos arquivos da pasta.

    Ordem: os locks (``uv.lock``, ``poetry.lock``, ``pdm.lock``) e o
    ``Pipfile``; depois o ``pyproject.toml`` (``[tool.poetry]`` é poetry,
    ``[tool.pdm]`` é pdm, qualquer outro é uv); depois o
    ``requirements.txt``; sem nada disso, o Python de quem roda o robô.

    Args:
        pasta: pasta do script do robô.

    Returns:
        A ferramenta e o arquivo que a identificou (vazio para o
        sistema).

    English:
        Finds the dependency manager from the folder's files.

        Order: the locks (``uv.lock``, ``poetry.lock``, ``pdm.lock``) and
        the ``Pipfile``; then ``pyproject.toml`` (``[tool.poetry]`` is
        poetry, ``[tool.pdm]`` is pdm, anything else is uv); then
        ``requirements.txt``; with none of these, the Python of whoever
        runs the robot.

        Args:
            pasta: the robot's script folder.

        Returns:
            The tool and the file that identified it (empty for the
            system).
    """
    for arquivo, ferramenta in MARCADORES:
        if (pasta / arquivo).is_file():
            return ferramenta, arquivo

    pyproject = pasta / "pyproject.toml"
    if pyproject.is_file():
        try:
            secoes = tomllib.loads(pyproject.read_text()).get("tool", {})
        except tomllib.TOMLDecodeError, UnicodeDecodeError:
            secoes = {}
        if "poetry" in secoes:
            return Ferramenta.POETRY, "pyproject.toml [tool.poetry]"
        if "pdm" in secoes:
            return Ferramenta.PDM, "pyproject.toml [tool.pdm]"
        return Ferramenta.UV, "pyproject.toml"

    if (pasta / "requirements.txt").is_file():
        return Ferramenta.PIP, "requirements.txt"
    return Ferramenta.SISTEMA, ""


def nome_do_venv(pasta_robos: Path, pasta_do_robo: Path) -> str:
    """Dá a cada robô um nome de ambiente a partir do caminho dele.

    ``coleta/notas`` vira ``coleta__notas``; um robô direto na pasta
    aprovada vira ``_raiz``. É o mesmo nome que o agente em Go usa.

    Args:
        pasta_robos: pasta aprovada.
        pasta_do_robo: pasta do script do robô.

    Returns:
        O nome da pasta do ambiente do robô.

    English:
        Gives each robot an environment name from its path.

        ``coleta/notas`` becomes ``coleta__notas``; a robot straight in
        the approved folder becomes ``_raiz``. It is the same name the Go
        agent uses.

        Args:
            pasta_robos: approved folder.
            pasta_do_robo: the robot's script folder.

        Returns:
            The name of the robot's environment folder.
    """
    relativo = pasta_do_robo.resolve().relative_to(pasta_robos.resolve())
    return "__".join(relativo.parts) or "_raiz"


def ambiente_limpo(
    base: Mapping[str, str], venv_atual: str | None = None
) -> dict[str, str]:
    """Copia o ambiente de quem roda o robô, sem o que não deve vazar.

    Tira as variáveis de ``VARIAVEIS_REMOVIDAS`` e a pasta ``bin`` do
    venv atual do ``PATH`` (no Docker do Maestro, ``/opt/venv/bin`` vem
    antes de tudo no ``PATH``), e liga a saída do Python sem buffer.

    Args:
        base: ambiente de quem roda o robô.
        venv_atual: venv em que quem roda o robô está, se houver.

    Returns:
        O ambiente do robô.

    English:
        Copies the environment of whoever runs the robot, without what
        must not leak.

        Removes the variables in ``VARIAVEIS_REMOVIDAS`` and the current
        venv's ``bin`` folder from ``PATH`` (in Maestro's Docker,
        ``/opt/venv/bin`` comes first in ``PATH``), and turns on
        unbuffered Python output.

        Args:
            base: environment of whoever runs the robot.
            venv_atual: venv whoever runs the robot is in, if any.

        Returns:
            The robot's environment.
    """
    ambiente = {
        nome: valor
        for nome, valor in base.items()
        if nome not in VARIAVEIS_REMOVIDAS
    }
    venvs = {v for v in (venv_atual, base.get("VIRTUAL_ENV")) if v}
    bins = {str(Path(venv) / "bin") for venv in venvs}
    if "PATH" in ambiente and bins:
        ambiente["PATH"] = os.pathsep.join(
            parte
            for parte in ambiente["PATH"].split(os.pathsep)
            if parte.rstrip("/") not in bins
        )
    ambiente["PYTHONUNBUFFERED"] = "1"
    return ambiente


def planejar(
    script: Path,
    programas: Programas,
    pasta_robos: Path,
    pasta_venvs: Path | None = None,
) -> Plano:
    """Monta o plano de preparo e execução do robô.

    Com ``pasta_venvs``, o ambiente de cada robô fica fora da pasta dele,
    em ``pasta_venvs/<nome do robô>``, cada ferramenta com a sua
    variável; o pdm, que não tem essa variável, usa a pasta de venvs
    dele, também fora da pasta do robô. Sem ``pasta_venvs``, cada
    ferramenta usa o próprio padrão (o ``.venv`` da pasta, no uv e no
    pip).

    Args:
        script: caminho absoluto do script, já resolvido na pasta
            aprovada.
        programas: programas de cada ferramenta.
        pasta_robos: pasta aprovada.
        pasta_venvs: onde guardar os ambientes, se não na pasta do robô.

    Returns:
        O plano do robô.

    English:
        Builds the robot's preparation and run plan.

        With ``pasta_venvs``, each robot's environment lives outside its
        folder, in ``pasta_venvs/<robot name>``, each tool with its own
        variable; pdm, which has no such variable, uses its own venvs
        folder, also outside the robot's folder. Without ``pasta_venvs``,
        each tool uses its own default (the folder's ``.venv``, for uv and
        pip).

        Args:
            script: absolute script path, already resolved in the
                approved folder.
            programas: each tool's programs.
            pasta_robos: approved folder.
            pasta_venvs: where to keep the environments, if not in the
                robot's folder.

        Returns:
            The robot's plan.
    """
    pasta = script.parent
    ferramenta, origem = detectar(pasta)
    venv = (
        pasta_venvs / nome_do_venv(pasta_robos, pasta) if pasta_venvs else None
    )

    match ferramenta:
        case Ferramenta.UV:
            env = {"UV_PROJECT_ENVIRONMENT": str(venv)} if venv else {}
            uv = programas.uv
            return Plano(
                ferramenta,
                origem,
                pasta,
                uv,
                [[uv, "sync"]],
                [uv, "run", "--no-sync", "python"],
                env,
            )
        case Ferramenta.POETRY:
            env = {"POETRY_NO_INTERACTION": "1"}
            if venv:
                env |= {
                    "POETRY_VIRTUALENVS_IN_PROJECT": "false",
                    "POETRY_VIRTUALENVS_PATH": str(venv),
                }
            poetry = programas.poetry
            return Plano(
                ferramenta,
                origem,
                pasta,
                poetry,
                [[poetry, "install", "--no-root"]],
                [poetry, "run", "python"],
                env,
            )
        case Ferramenta.PDM:
            # O pdm não tem variável para a pasta dos venvs: fora do
            # projeto, o venv vai para a pasta de venvs do próprio pdm,
            # dentro do HOME.
            env = {"PDM_NON_INTERACTIVE": "1"}
            if venv:
                env["PDM_VENV_IN_PROJECT"] = "false"
            pdm = programas.pdm
            return Plano(
                ferramenta,
                origem,
                pasta,
                pdm,
                [[pdm, "install"]],
                [pdm, "run", "python"],
                env,
            )
        case Ferramenta.PIPENV:
            env = {"PIPENV_NOSPIN": "1", "PIPENV_IGNORE_VIRTUALENVS": "1"}
            if venv:
                env["WORKON_HOME"] = str(venv)
            pipenv = programas.pipenv
            sincronizar = (
                "sync" if (pasta / "Pipfile.lock").is_file() else "install"
            )
            return Plano(
                ferramenta,
                origem,
                pasta,
                pipenv,
                [[pipenv, sincronizar]],
                [pipenv, "run", "python"],
                env,
            )
        case Ferramenta.PIP:
            ambiente_pip = venv or pasta / ".venv"
            python_do_venv = str(_python_do_venv(ambiente_pip))
            preparo = []
            if not _python_do_venv(ambiente_pip).exists():
                preparo.append(
                    [programas.python, "-m", "venv", str(ambiente_pip)]
                )
            preparo.append(
                [
                    python_do_venv,
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "-r",
                    "requirements.txt",
                ]
            )
            return Plano(
                ferramenta, origem, pasta, None, preparo, [python_do_venv]
            )
        case _:
            return Plano(
                ferramenta, origem, pasta, None, [], [programas.python]
            )


def rodar_robo(
    script: Path,
    *,
    programas: Programas,
    pasta_robos: Path,
    timeout_segundos: float,
    deve_parar: Callable[[], bool],
    ao_receber_linha: Callable[[str], None],
    a_cada_volta: Callable[[], None] | None = None,
    pasta_venvs: Path | None = None,
    ambiente_base: Mapping[str, str] | None = None,
    venv_atual: str | None = None,
    timeout_preparo: float = TEMPO_MAXIMO_PREPARO_SEGUNDOS,
) -> tuple[Motivo, int | None]:
    """Detecta a ferramenta, prepara as dependências e roda o robô.

    Tudo vai para o log da execução: uma linha ``[ambiente]`` dizendo o
    que foi detectado, cada comando de preparo e a saída dele, e então a
    saída do robô. O tempo limite do robô conta só a execução dele; o
    preparo tem o próprio limite (``timeout_preparo``), porque a primeira
    instalação de um robô pode demorar bem mais que ele.

    - Ferramenta não instalada (ou ambiente que não abre):
      ``AMBIENTE_INVALIDO``, sem nova tentativa.
    - Preparo que falha ou passa do limite: ``PREPARO_FALHOU``, com nova
      tentativa (costuma ser rede).
    - Parada pedida no preparo ou na execução: ``PARADO``.

    Args:
        script: caminho absoluto do script, já resolvido na pasta
            aprovada.
        programas: programas de cada ferramenta.
        pasta_robos: pasta aprovada.
        timeout_segundos: tempo máximo da execução do robô.
        deve_parar: função perguntada a cada segundo.
        ao_receber_linha: função chamada com cada linha do log.
        a_cada_volta: função chamada a cada volta do laço do executor.
        pasta_venvs: onde guardar os ambientes, se não na pasta do robô.
        ambiente_base: ambiente de quem roda o robô; ``None`` usa o do
            processo atual.
        venv_atual: venv de quem roda o robô, tirado do ``PATH``.
        timeout_preparo: tempo máximo de cada comando de preparo.

    Returns:
        O motivo do fim e o código de saída, se algo chegou a rodar.

    English:
        Detects the tool, prepares the dependencies and runs the robot.

        Everything goes into the execution log: an ``[ambiente]`` line
        saying what was detected, each preparation command and its
        output, and then the robot's output. The robot's timeout counts
        only its own run; preparation has its own limit
        (``timeout_preparo``), because a robot's first install can take
        much longer than the robot.

        - Tool not installed (or an environment that will not start):
          ``AMBIENTE_INVALIDO``, with no new attempt.
        - Preparation that fails or goes past the limit:
          ``PREPARO_FALHOU``, with a new attempt (usually the network).
        - Stop requested during preparation or run: ``PARADO``.

        Args:
            script: absolute script path, already resolved in the
                approved folder.
            programas: each tool's programs.
            pasta_robos: approved folder.
            timeout_segundos: maximum time of the robot's run.
            deve_parar: function asked every second.
            ao_receber_linha: function called with each log line.
            a_cada_volta: function called on every executor loop turn.
            pasta_venvs: where to keep the environments, if not in the
                robot's folder.
            ambiente_base: environment of whoever runs the robot;
                ``None`` uses the current process's.
            venv_atual: venv of whoever runs the robot, removed from
                ``PATH``.
            timeout_preparo: maximum time of each preparation command.

        Returns:
            Why it ended and the exit code, if something got to run.
    """
    plano = planejar(script, programas, pasta_robos, pasta_venvs)
    env = (
        ambiente_limpo(
            os.environ if ambiente_base is None else ambiente_base, venv_atual
        )
        | plano.env
    )

    if plano.ferramenta is Ferramenta.SISTEMA:
        ao_receber_linha(
            f"{PREFIXO} sem gerenciador de dependências; "
            f"rodando com {plano.python[0]}"
        )
    else:
        ao_receber_linha(f"{PREFIXO} {plano.ferramenta} ({plano.origem})")
    if plano.programa and not shutil.which(
        plano.programa, path=env.get("PATH")
    ):
        ao_receber_linha(
            f"{PREFIXO} o robô usa {plano.ferramenta}, mas "
            f"'{plano.programa}' não está instalado nesta máquina"
        )
        return Motivo.AMBIENTE_INVALIDO, None

    try:
        for passo in plano.preparo:
            ao_receber_linha(f"{PREFIXO} $ {' '.join(passo)}")
            preparo = executar(
                passo,
                plano.pasta,
                timeout_preparo,
                deve_parar,
                ao_receber_linha,
                a_cada_volta,
                env,
            )
            if preparo.motivo is Motivo.PARADO:
                return Motivo.PARADO, preparo.codigo_saida
            if preparo.motivo is Motivo.TEMPO_ESGOTADO:
                ao_receber_linha(
                    f"{PREFIXO} preparo excedeu o limite de "
                    f"{timeout_preparo:.0f}s"
                )
                return Motivo.PREPARO_FALHOU, preparo.codigo_saida
            if preparo.codigo_saida != 0:
                ao_receber_linha(
                    f"{PREFIXO} preparo falhou (código {preparo.codigo_saida})"
                )
                return Motivo.PREPARO_FALHOU, preparo.codigo_saida

        resultado = executar(
            plano.comando(script),
            plano.pasta,
            timeout_segundos,
            deve_parar,
            ao_receber_linha,
            a_cada_volta,
            env,
        )
    except OSError as erro:
        ao_receber_linha(f"{PREFIXO} o ambiente do robô não abriu: {erro}")
        return Motivo.AMBIENTE_INVALIDO, None
    return resultado.motivo, resultado.codigo_saida


def _python_do_venv(venv: Path) -> Path:
    """Retorna o Python de um venv, no Windows ou nos outros sistemas.

    Args:
        venv: pasta do venv.

    Returns:
        O caminho do executável do Python dentro do venv.

    English:
        Returns a venv's Python, on Windows or other systems.

        Args:
            venv: venv folder.

        Returns:
            The path to the Python executable inside the venv.
    """
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"
