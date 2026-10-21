#!/bin/sh
# Baixa os navegadores do Playwright para cada robô da pasta aprovada que
# usa Playwright. Cada versão do Playwright espera a própria versão do
# navegador, por isso a instalação roda no ambiente de cada robô (o
# mesmo venv que o agente usa ao executá-lo).
#
# Uso, com o agente no ar:
#   docker compose exec agente instalar-navegadores            # firefox
#   docker compose exec agente instalar-navegadores chromium   # outro
set -eu

NAVEGADORES="${*:-firefox}"
PASTA_ROBOS="${AGENTE_PASTA_ROBOS:?AGENTE_PASTA_ROBOS não definida}"
PASTA_VENVS="${AGENTE_PASTA_VENVS:?AGENTE_PASTA_VENVS não definida}"

find "$PASTA_ROBOS" -maxdepth 4 -name pyproject.toml -not -path '*/.venv/*' |
while read -r projeto; do
    grep -qi playwright "$projeto" || continue
    pasta=$(dirname "$projeto")
    # Mesmo nome que o agente dá ao venv: caminho relativo com / -> __.
    nome=$(printf '%s' "${pasta#"$PASTA_ROBOS"/}" | sed 's#/#__#g')
    echo "==> $pasta"
    UV_PROJECT_ENVIRONMENT="$PASTA_VENVS/$nome" \
        uv run --directory "$pasta" playwright install $NAVEGADORES
done
