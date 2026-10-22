# Imagem do Maestro: a mesma para o servidor (Daphne) e para o worker
# (Celery). Em desenvolvimento, o docker-compose.yml monta o código em
# /app por cima do que foi copiado aqui, para as mudanças valerem sem
# reconstruir a imagem.
FROM python:3.14-slim

# Versões fixas dos gerenciadores de dependências dos robôs; para
# atualizar, troque aqui (as mesmas do agente-go/Dockerfile).
ARG POETRY_VERSAO=2.4.3
ARG PDM_VERSAO=2.29.3
ARG PIPENV_VERSAO=2026.10.2

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

# O worker roda os robôs sem agente e detecta o gerenciador de cada um
# pela pasta (robots/ambiente.py): uv já veio acima; poetry, pdm e
# pipenv ficam cada um no próprio ambiente em /opt/uv-tools, com o
# executável em /usr/local/bin, fora do venv do Maestro.
RUN export UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
       UV_CACHE_DIR=/tmp/uv-cache \
    && uv tool install "poetry==${POETRY_VERSAO}" \
    && uv tool install "pdm==${PDM_VERSAO}" \
    && uv tool install "pipenv==${PIPENV_VERSAO}" \
    && rm -rf /tmp/uv-cache

# Ambientes e caches dos robôs do worker (ROBOS_PASTA_VENVS e HOME no
# docker-compose.yml). Aberta a qualquer usuário porque o compose roda o
# container com o UID de quem o sobe; o volume herda essa permissão.
RUN mkdir -p /var/lib/maestro-robos && chmod 1777 /var/lib/maestro-robos

# O venv fica fora de /app: assim o .venv do host (montado junto com o
# código) não é usado nem sobrescrito pelo container.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependências primeiro: mudar o código não refaz esta camada.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
