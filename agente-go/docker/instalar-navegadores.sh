#!/bin/sh
# Baixa os navegadores do Playwright para cada robô da pasta aprovada que
# usa Playwright. Cada versão do Playwright espera a própria versão do
# navegador, por isso a instalação roda no ambiente de cada robô: o
# "agente ambiente" detecta o gerenciador de dependências da pasta (uv,
# poetry, pdm, pipenv ou pip), prepara as dependências e roda o Python
# daquele robô, o mesmo que o agente usa ao executá-lo.
#
# Uso, com o agente no ar:
#   docker compose exec agente instalar-navegadores            # firefox
#   docker compose exec agente instalar-navegadores chromium   # outro
set -eu

PASTA_ROBOS="${AGENTE_PASTA_ROBOS:?AGENTE_PASTA_ROBOS não definida}"

# Robôs que citam o playwright em algum arquivo de dependências.
find "$PASTA_ROBOS" -maxdepth 4 \
    \( -name pyproject.toml -o -name requirements.txt -o -name Pipfile \) \
    -not -path '*/.venv/*' -exec grep -lqi playwright {} \; -print |
xargs -r -n1 dirname | sort -u |
while read -r pasta; do
    echo "==> $pasta"
    # shellcheck disable=SC2086 # os navegadores vão como argumentos separados
    agente ambiente "${pasta#"$PASTA_ROBOS"/}" -- -m playwright install ${*:-firefox}
done
