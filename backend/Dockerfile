# syntax=docker/dockerfile:1.7
# Base image pinned by digest for reproducible/supply-chain-safe builds (3.13-slim).
# Dependabot's `docker` ecosystem keeps the digest fresh (see .github/dependabot.yml).
FROM python:3.13-slim@sha256:b04b5d7233d2ad9c379e22ea8927cd1378cd15c60d4ef876c065b25ea8fb3bf3 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

WORKDIR /app

# Deps before code so source edits don't bust the uv-sync layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --dev

# Bake the local embedding model into the image so Recall works offline at runtime.
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

COPY backend /app/backend

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

FROM base AS web

COPY backend/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000

# Containers run as root by design (single-user, 127.0.0.1-bound; the /data volume is
# root-owned, so a non-root USER would break snapshot/backup/secret writes). Mirrors the
# missing-user exclusion in .github/workflows/semgrep.yml.
# nosemgrep
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# nosemgrep
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker

# Playwright + chromium (~150MB) for snapshot chart rendering (M5).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
RUN uv run playwright install chromium --with-deps

# Root by design — see web stage.
# nosemgrep
CMD ["uv", "run", "celery", "-A", "config", "worker", "-l", "INFO"]
