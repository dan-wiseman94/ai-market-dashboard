# AI Trading Dashboard

Single-user desktop dashboard that captures stock-market snapshots (quotes, OHLC, option chains, news, rendered charts) and routes them to an AI — **Claude**, **OpenAI**, or a **local OpenAI-compatible endpoint** — for observations framed by a named trading style and a per-snapshot objective.

**Observational only.** No broker write path. Runs entirely in Docker Compose and binds to `127.0.0.1`.

> Full design: [`docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`](docs/superpowers/specs/2026-04-16-ai-dashboard-design.md)
> Contributor guide: [`CLAUDE.md`](CLAUDE.md)

## Status

**v1 feature set complete — M1 through M8 all shipped.**

| Milestone | Scope | Tag |
|---|---|---|
| M1 | Compose skeleton | `m1-skeleton` |
| M2 | Market data (Schwab) | |
| M3 | Snapshots + AI routing | |
| M4 | Threads + streaming + compare | |
| M5 | Option chains, news, chart images | |
| M6 | Observer (scheduled AI runs) | `m6-observer` |
| M7 | Event triggers + condition DSL | |
| M8 | Polish (layout, cost caps, backups, export) | `m8-polish` |

## Prerequisites

- Docker + Docker Compose v2.29+
- For the Schwab market-data integration: a developer app at <https://developer.schwab.com> with callback `https://127.0.0.1:8000/api/schwab/callback`
- *(Optional, for editor tooling outside Docker)* Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 20+

## Quick start

```bash
cp .env.example .env

# Generate a Django secret key and paste into DJANGO_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(50))"

# (Optional) Add Schwab + provider API keys to .env

make dev        # docker compose up --watch (hot reload)
```

First run builds images (3–8 minutes). Then:

- **Frontend (dev, Vite):** <http://localhost:5173>
- **Django API + WebSockets:** <http://localhost:8000>

On first boot, a single-user API token is written to `/data/user.token` inside the `web` container — there is no password UI.

## Common commands

| Command | Purpose |
|---|---|
| `make dev` | Start full stack with hot reload |
| `make shell` | Bash inside the `web` container |
| `make migrate` / `make makemigrations` | Django migrations |
| `make test` | `pytest` + `vitest --run` |
| `make lint` | ruff + ruff format check + ty + eslint |
| `make fmt` | ruff format + ruff --fix |
| `make check` | lint + test (what CI runs) |
| `make logs s=<service>` | Tail a service: `web`, `worker`, `beat`, `redis`, `db`, `frontend` |
| `make down` | Stop containers (volumes kept) |
| `make prod` | Dev + prod overlay — frontend baked in, served by Whitenoise |
| `make e2e` | Start stack with `compose.e2e.yaml` (mocks external APIs), run Playwright journeys, tear down |
| `make e2e-one t=<mod>` | Run one E2E journey (requires overlay already up) |
| `make restore file=<name>` | Restore Postgres from `/data/backups/<name>` |

Run a single backend test:

```bash
docker compose exec web pytest backend/apps/<app>/tests/test_<x>.py::<name> -v
```

Integration tests are excluded by default (`-m 'not integration'`); run them with `pytest -m integration`.

## Architecture at a glance

Six services in `compose.yaml`, all bound to `127.0.0.1`:

```
web       Django + DRF + Channels (Daphne ASGI)   :8000
worker    Celery worker (has chromium for chart renders)
beat      Celery beat (DatabaseScheduler)
redis     Broker + Channels layer + cache         :6379
db        Postgres 16                             :5432
frontend  Vite dev server (React + TS)            :5173
```

Backend code lives under `backend/apps/<name>/` (imported as `apps.<name>`):

- `core` · health, base consumer, logging
- `market` · Schwab client, quotes/OHLC/chain/news
- `snapshots` · capture orchestration + token budget
- `ai` · provider abstraction (Claude / OpenAI / Local), router, catalog, cost calc
- `threads` · messages, streaming consumer, multi-provider compare
- `observer` · scheduled AI runs via Celery beat
- `triggers` · event-trigger evaluator + condition DSL + firings
- `profiles` · trading-style profiles
- `secrets` · encrypted credentials (Schwab OAuth, API keys) + cost caps
- `costs` · per-provider / per-model / per-thread aggregation, caps, CSV export
- `backups` · scheduled `pg_dump` + rotation
- `export` · async zip bundles (threads, snapshots, observations, triggers, profiles)

WebSocket groups: `user.<id>.notifications`, `thread.<id>`, `snapshot.<id>`. See design spec §3.3.

## Layout

```
backend/             Django project (config/) + apps/
frontend/            Vite + React + TypeScript
docs/superpowers/
  specs/             Design docs
  plans/             Per-milestone implementation plans
e2e/                 Playwright end-to-end tests
compose.yaml         Dev stack
compose.prod.yaml    Prod overlay (static frontend via Whitenoise)
compose.e2e.yaml     E2E harness
```

## Production mode

```bash
docker compose -f compose.yaml -f compose.prod.yaml --profile build run --rm frontend-build
docker compose -f compose.yaml -f compose.prod.yaml up
```

Frontend is built once, then served by Django/Whitenoise on <http://localhost:8000>. The SPA currently mounts at `/static/index.html` (see CLAUDE.md — M1 carry-over, fix planned in M8).

## Security notes

- Services bind to `127.0.0.1` only — do not expose this stack publicly.
- Schwab OAuth tokens and provider API keys are encrypted at rest via `django-cryptography`; the key is derived from `DJANGO_SECRET_KEY` + `/data/secret.salt`. Rotating `DJANGO_SECRET_KEY` invalidates stored secrets.
- Image payloads (chart PNGs) live in Postgres (`SnapshotImage.data`), capped at 5 MB.
