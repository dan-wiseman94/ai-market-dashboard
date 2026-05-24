# AI Trading Dashboard

Single-user desktop dashboard that captures stock-market snapshots (quotes, OHLC, option chains, positions, market breadth, news, rendered charts) and routes them to an AI — **Claude**, **OpenAI**, or a **local OpenAI-compatible endpoint** — for observations framed by a named trading style and a per-snapshot objective.

**Observational only.** No broker write path. Runs entirely in Docker Compose and binds to `127.0.0.1`.

> Full design: [`docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`](docs/superpowers/specs/2026-04-16-ai-dashboard-design.md)
> Contributor guide: [`CLAUDE.md`](CLAUDE.md)

## Status

**Feature-complete — all milestones shipped (M1 → M10, plus M12 analytics; there is no M11).**

| Milestone | Scope | Tag |
|---|---|---|
| M1 | Compose skeleton | `m1-skeleton` |
| M2 | Market data (Schwab) | `m2-market-data` |
| M3 | Snapshots + AI routing | `m3-snapshots-ai` |
| M4 | Threads + streaming + compare | `m4-full-threads` |
| M5 | Option chains, news, chart images | `m5-chains-news-images` |
| M6 | Observer (scheduled AI runs) | `m6-observer` |
| M7 | Event triggers + condition DSL | `m7-event-triggers` |
| M8 | Polish (layout, cost caps, backups, export) | `m8-polish` |
| M9 | AI platform v2 (tool use, extended thinking, memory) | `m9-ai-platform-v2` |
| M10 | AI platform v2.5 (files, citations, structured, batch) | `m10-ai-platform-v25` |
| M12 | Analytics (leaderboard, heatmap, unusual options) | `m12-analytics` |

## Features

### Market data & snapshots

- **Snapshots** — capture a point-in-time market picture from opt-in sections: real-time **quotes**, **OHLC** history, **option chains**, **positions**, **market breadth**, **news**, and **rendered chart images** (headless-Chromium PNGs). A section that fails is marked `failed` and explicitly flagged in the AI payload — partial captures are fine, never silently dropped.
- **Watchlists** — group tickers and drill into a per-ticker market page.
- **Objective + profile framing** — every capture carries a free-text objective and a named trading-style profile, so the model knows *how* to look and *what* you're asking.
- **Token budgeting** — the payload is trimmed to a per-model budget (from the model catalog) before it reaches the LLM; per-section token counts are recorded for the cost drill-down.
- **Snapshot diff** — `GET /api/snapshots/<id>/diff/?against=<id>` returns a markdown delta between two captures.

### AI providers & routing

- **Three backends** — Claude (Anthropic SDK), OpenAI, and any local OpenAI-compatible endpoint. A normalized event stream (`text_delta | image_ref | usage | done | error`) keeps the rest of the app provider-agnostic.
- **Router with precedence** — provider/model selection flows through a single router + factory; providers are never instantiated ad-hoc from views or tasks.
- **Model catalog** — per-model pricing and max payload budgets drive both cost calculation and payload trimming.
- **Trading-style profiles** — reusable personas (system framing) that also toggle the advanced Claude capabilities below.

### Threads & streaming

- **Live token streaming** over WebSockets (`thread.<id>`): full message lifecycle plus `text_delta` and post-completion `cost` events.
- **Multi-provider compare** — `POST /api/threads/<id>/compare` fans the same prompt across multiple provider+model pairs in parallel, each streaming into its own branch tab.
- **Stop** — aborts the upstream generation *and* billing (closes the provider stream), not just the final write.
- **Pinned snapshots** — a captured snapshot is injected as the thread's first turn, so the model (and you) can see exactly what it was given.

### Advanced Claude capabilities (opt-in per profile)

- **Tool use** — an agentic tool loop backed by a pluggable tool registry; every call is recorded and streamed (`tool_call` / `tool_result`).
- **Extended thinking** — budgeted reasoning with `thinking_delta` events (billed as output tokens).
- **Memory** — the `memory_20250818` tool, scoped to a per-profile directory under `/data/memory/<profile_id>/`.
- **Files** — upload documents through the Anthropic Files API and attach them to a thread.
- **Citations** — news items are sent as Anthropic `search_result` blocks; the UI resolves citations back to their source.
- **Prompt caching** — multi-turn Claude runs cache the prior message for ~0.1× input cost on a hit.
- **Structured observations** — observer runs can return a typed `ObservationReport` for structured UI cards.

> OpenAI / Local providers ignore the advanced toggles — enabling them on a non-Claude profile is a silent no-op (parity is a future milestone).

### Observer — scheduled AI runs

- **Cron schedules** drive Celery beat; expressions evaluate in a configurable timezone (`OBSERVER_BEAT_TIMEZONE`, with ET cron presets in the UI).
- **Three orthogonal modes** — `structured` (typed report), `diff` (feed only the delta vs. the prior snapshot), and `batch` (Anthropic Messages Batch — ~50% cheaper, no streaming during the window).
- **Market-hours aware** via the NYSE calendar (holidays + half-days correct).
- **Timeline** view of every fire; completions and errors push notifications.

### Event triggers

- **Condition DSL** — JSON with top-level `all` / `any` / `not` and metric leaves (`metric`, `ticker`, `op`, `value`, `window`).
- **Evaluator** runs every ~10s on Celery beat — not a long-running process.
- **Backtest** — `POST /api/triggers/backtest/` replays a condition over stored OHLC bars and returns the matching timestamps.
- **Firings** are recorded and pushed as notifications.

### Cost tracking

- **Aggregation** per provider, per model, and per thread.
- **Daily + monthly caps** (opt-in) enforced across threads, observer, and triggers.
- **CSV export** and a **per-snapshot cost drill-down** that attributes token cost to each captured section.

### Analytics (on-demand)

- **Provider leaderboard** — correlates each run against the snapshot's primary ticker using stored OHLC at capture vs. capture + N hours, with an honest `coverage_pct` when price history is missing.
- **Cost per insight**, **trigger heatmap**, and an **observer timeline** built from message history.
- **Unusual-options detector** — flags chain lines on volume/OI or IV-z outliers, returning a per-line reason for *why* each was flagged.

### Operations & UX

- **Backups** — scheduled `pg_dump` with rotation; `make restore file=<name>` to roll back.
- **Export** — async zip bundles of threads, snapshots, observations, triggers, profiles, and watchlists.
- **App shell** — shared layout with top/side nav, breadcrumbs, a notification bell, and a live connection-status dot.
- **Command palette** (`Cmd`/`Ctrl`-K) and `g <x>` keyboard shortcuts to every top-level route.
- **Encrypted secrets** — Schwab OAuth tokens and provider API keys are stored encrypted at rest.

## Prerequisites

- Docker + Docker Compose v2.29+
- For the Schwab market-data integration: a developer app at <https://developer.schwab.com> with callback `https://127.0.0.1:8000/api/schwab/callback`
- *(Optional, for editor tooling outside Docker)* Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 20+

## Quick start

```bash
cp .env.example .env

# Generate a Django secret key and paste into DJANGO_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(50))"

# (Optional) Add Schwab OAuth client credentials to .env

make dev        # docker compose up --watch (hot reload)
```

First run builds images (3–8 minutes). Then:

- **Frontend (dev, Vite):** <http://localhost:5173>
- **Django API + WebSockets:** <http://localhost:8000>

There is no login screen — the stack is single-user and protected by network isolation (see [Security notes](#security-notes)). **Provider API keys** (Claude / OpenAI) are entered in-app under **Settings** and stored encrypted — *not* in `.env`. Only Schwab OAuth client credentials live in `.env`.

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
| `make e2e` | Start the e2e stack (mocks external APIs), run the `ui`/`api`/`ws`/`visual`/`a11y` lanes, tear down |
| `make e2e-perf` | Run the performance lane against the prod overlay |
| `make e2e-visual-update` | Regenerate visual-regression baselines under `e2e/visual/__screenshots__/` |
| `make e2e-one t=<mod>` | Run one E2E test file (overlay must be up: `make e2e-up`) |
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

- `core` · health, base consumer, logging, `MOCK_EXTERNAL` flag
- `market` · Schwab client, quotes/OHLC/chain/news
- `snapshots` · capture orchestration + token budget
- `ai` · provider abstraction (Claude / OpenAI / Local), router, catalog, cost calc, tool/thinking/memory/citations support
- `threads` · messages, streaming consumer, multi-provider compare, stop, file attach
- `observer` · scheduled AI runs via Celery beat (structured / diff / batch modes)
- `triggers` · event-trigger evaluator + condition DSL + firings + backtest
- `profiles` · trading-style profiles
- `secrets` · encrypted credentials (Schwab OAuth, provider API keys) + cost caps
- `costs` · per-provider / per-model / per-thread aggregation, caps, CSV export, snapshot drill-down
- `analytics` · on-demand aggregations (leaderboard, cost-per-insight, trigger heatmap, observer timeline, unusual options)
- `files` · Anthropic Files API proxy (upload + attach to threads)
- `backups` · scheduled `pg_dump` + rotation
- `export` · async zip bundles (threads, snapshots, observations, triggers, profiles, watchlists)

WebSocket groups: `user.<id>.notifications`, `thread.<id>`, `snapshot.<id>`. See design spec §3.3.

## Layout

```
backend/             Django project (config/) + apps/
frontend/            Vite + React + TypeScript
docs/superpowers/
  specs/             Design docs
  plans/             Per-milestone implementation plans
e2e/                 Six-lane end-to-end suite (ui/api/ws/visual/a11y/perf)
compose.yaml         Dev stack
compose.prod.yaml    Prod overlay (static frontend via Whitenoise)
compose.e2e.yaml     E2E harness (MOCK_EXTERNAL=true)
```

## Production mode

```bash
# 1. Build the static frontend into frontend/dist
docker compose -f compose.yaml -f compose.prod.yaml --profile build run --rm frontend-build

# 2. Start the prod stack (Django/Whitenoise serves the built SPA)
make prod
```

The SPA is served at <http://localhost:8000>. Prod `/` serves `index.html` via Whitenoise (`WHITENOISE_INDEX_FILE`) plus a Django `TemplateView` catch-all in `config/urls.py` (excluding `api/|static/|render/|ws/|admin/`), so deep links and refreshes work.

## Security notes

- **No app-level authentication.** Security is network isolation: the stack binds to `127.0.0.1` only and every API/WS endpoint defaults to `AllowAny`. WebSocket connections are Origin-validated against `ALLOWED_HOSTS` (`AllowedHostsOriginValidator`). **Do not bind to `0.0.0.0` without first adding real authentication** — and do not expose this stack publicly.
- Schwab OAuth tokens and provider API keys are encrypted at rest via `django-cryptography`; the key is derived from `DJANGO_SECRET_KEY` + `/data/secret.salt`. Rotating `DJANGO_SECRET_KEY` invalidates stored secrets.
- Image payloads (chart PNGs) live in Postgres (`SnapshotImage.data`), capped at 5 MB.
