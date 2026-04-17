# AI Trading Dashboard

Single-user desktop dashboard that captures market snapshots and routes them to Claude / OpenAI / local AI for analysis. See `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` for the design.

## Prerequisites
- Docker + Docker Compose v2.29+
- (For local dev outside Docker, optional) Python 3.12 + uv, Node 20+

## Quick start

```bash
cp .env.example .env
# Generate a Django secret key and paste into .env
python -c "import secrets; print(secrets.token_urlsafe(50))"

make dev      # docker compose up --watch (hot reload)
```

Open http://localhost:5173 (frontend, dev) or http://localhost:8000 (Django + prod frontend).

## Common commands

| Command | Purpose |
|---|---|
| `make dev` | Start full stack with hot reload |
| `make migrate` | Run Django migrations |
| `make shell` | Bash shell inside the web container |
| `make test` | Full test suite (pytest + vitest) |
| `make lint` | ruff + mypy + eslint |
| `make check` | lint + test (what CI runs) |
| `make logs s=worker` | Tail logs for a service |
| `make down` | Stop and remove containers |

## Layout
- `backend/` — Django project (`config/`) + apps (`apps/`)
- `frontend/` — Vite + React + TypeScript
- `docs/superpowers/specs/` — design docs
- `docs/superpowers/plans/` — implementation plans

## Production mode

```bash
docker compose -f compose.yaml -f compose.prod.yaml --profile build run --rm frontend-build
docker compose -f compose.yaml -f compose.prod.yaml up
```

Frontend is built once, then served by Django through Whitenoise on http://localhost:8000.
