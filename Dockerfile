# Imagem do Maestro: a mesma para o servidor (Daphne) e para o worker
# (Celery). Em desenvolvimento, o docker-compose.yml monta o código em
# /app por cima do que foi copiado aqui, para as mudanças valerem sem
# reconstruir a imagem.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /bin/

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
