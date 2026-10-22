# Imagem do agente: o binário em Go mais o que os robôs precisam para
# rodar (Python 3.14, os gerenciadores de dependências que o agente
# detecta em cada robô — uv, poetry, pdm e pipenv — e as bibliotecas de
# sistema dos navegadores do Playwright). Ubuntu 24.04 porque é a
# plataforma suportada pelo Playwright.

FROM golang:1.24-bookworm AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /agente .

FROM ubuntu:24.04

# Versões fixas dos gerenciadores, para a imagem não mudar sozinha entre
# uma construção e outra. Para atualizar, troque aqui.
ARG POETRY_VERSAO=2.4.3
ARG PDM_VERSAO=2.29.3
ARG PIPENV_VERSAO=2026.10.2

COPY --from=ghcr.io/astral-sh/uv:0.12.20 /uv /uvx /usr/local/bin/

# /var/lib/agente vira um volume: cache do uv, venvs dos robôs e
# navegadores sobrevivem a recriar o container.
ENV HOME=/var/lib/agente \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    UV_CACHE_DIR=/var/lib/agente/cache \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/var/lib/agente/navegadores

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python 3.14 (os robôs pedem >=3.14) e as dependências de sistema do
# Firefox e do Chromium. Os navegadores em si dependem da versão do
# Playwright de cada robô e são baixados depois, no volume
# (instalar-navegadores).
RUN uv python install 3.14 \
    && ln -s "$(uv python find 3.14)" /usr/local/bin/python3 \
    && UV_CACHE_DIR=/tmp/uv-cache uvx --python 3.14 --from playwright \
       playwright install-deps firefox chromium \
    && rm -rf /tmp/uv-cache /var/lib/apt/lists/*

# poetry, pdm e pipenv, cada um no próprio ambiente isolado em
# /opt/uv-tools, com o executável em /usr/local/bin. O agente escolhe
# qual usar pelos arquivos da pasta de cada robô (poetry.lock, pdm.lock,
# Pipfile...). Os ambientes e caches deles ficam no volume
# /var/lib/agente (HOME e AGENTE_PASTA_VENVS).
RUN export UV_TOOL_DIR=/opt/uv-tools UV_TOOL_BIN_DIR=/usr/local/bin \
       UV_CACHE_DIR=/tmp/uv-cache \
    && uv tool install --python 3.14 "poetry==${POETRY_VERSAO}" \
    && uv tool install --python 3.14 "pdm==${PDM_VERSAO}" \
    && uv tool install --python 3.14 "pipenv==${PIPENV_VERSAO}" \
    && rm -rf /tmp/uv-cache

COPY docker/instalar-navegadores.sh /usr/local/bin/instalar-navegadores
COPY --from=build /agente /usr/local/bin/agente

# O usuário 1000 (o "ubuntu" da imagem) é o mesmo dono das pastas do
# host: o que os robôs gravarem na pasta montada continua sendo seu.
RUN chmod +x /usr/local/bin/instalar-navegadores \
    && mkdir -p /var/lib/agente \
    && chown -R 1000:1000 /var/lib/agente /opt/uv-python /opt/uv-tools
USER 1000:1000

ENTRYPOINT ["agente"]
