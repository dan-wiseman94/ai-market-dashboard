# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-user desktop dashboard that captures snapshots of the stock market and routes them to a chosen AI (Claude / OpenAI / local OpenAI-compatible endpoint) for observations framed by a named trading style and per-snapshot objective. Strictly observational — no broker write path. Runs entirely in Docker Compose.

The design lives in `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`. Milestone plans live in `docs/superpowers/plans/`. Both are load-bearing — read the relevant spec section before adding a feature, and read the active milestone plan before starting new implementation work.

Milestones M1 (skeleton, tagged `m1-skeleton`) → M8 (polish). Each gets its own plan and is independently shippable. **Current status:** M1–M5 shipped (`m5-chains-news-images`); **next: M6 (observer)** — schedules + beat + observer timeline UI.

## Daily commands

Everything runs through Docker; Make targets wrap Compose.

| Command | What it does |
|---|---|
| `make dev` | Up the whole stack with `compose up --watch` (hot reload). First run: 3–8 min to build images. |
| `make shell` | Bash in the `web` container. Useful for ad-hoc `manage.py` commands. |
| `make migrate` / `make makemigrations` | Django migrations inside `web`. |
| `make test` | `pytest` in `web` + `vitest --run` in `frontend`. |
| `make lint` | `ruff check .` + `mypy .` in `web` + `npm run lint` in `frontend`. |
| `make check` | `lint` + `test` (what CI runs). |
| `make logs s=<service>` | Tail a service. Services: `web`, `worker`, `beat`, `redis`, `db`, `frontend`. |
| `make down` | Stop and remove containers (volumes kept). |
| `make prod` | Dev + prod compose overlay — frontend baked in, served by Django/Whitenoise on `:8000`. |

Run one backend test: `docker compose exec web pytest backend/apps/<app>/tests/test_<x>.py::<test_name> -v`

Run one frontend test: `docker compose exec frontend npx vitest run src/__tests__/App.test.tsx -t "specific test name"`

Full fresh-rebuild (wipes volumes, catches reproducibility bugs): `docker compose down -v && docker compose build --no-cache && docker compose up -d`

## Architecture big picture

**Six-service compose stack** (dev): `web` (Django + DRF + Channels via Daphne), `worker` (Celery), `beat` (Celery beat with `django_celery_beat.schedulers:DatabaseScheduler`), `redis` (broker + Channels layer + cache), `db` (Postgres 16), `frontend` (Vite dev server). Everything binds to `127.0.0.1` only.

**Django project** is `backend/config/` with settings split into `base.py` / `dev.py` / `prod.py`. Apps live under `backend/apps/<name>/` and are imported as `apps.<name>` (PYTHONPATH is `/app/backend` inside containers). Celery app lives at `config.celery` and is re-exported from `config/__init__.py` so `@shared_task` discovery works. Channels routing lives at `config.routing` and is mounted by `config.asgi`. Celery task packages are listed **explicitly** in `config/celery.py` (not autodiscovered) — a past silent-failure made autodiscovery untrustworthy; add new task modules to that list.

**App roster** (`backend/apps/`): `core` (health, base consumer, logging), `market` (Schwab client, quotes/OHLC/chain/news models, cache), `snapshots` (capture services + token budget), `ai` (providers, router, catalog, cost calc), `threads` (message model, consumer, compare endpoint), `costs` (per-provider usage aggregation), `profiles` (trading-style profiles), `secrets` (encrypted credential storage + Schwab OAuth).

**Adding a Django app:** create `backend/apps/<name>/` with `__init__.py`, `apps.py` (`AppConfig` with `name = "apps.<name>"`, short `label`), `urls.py`, `views.py` (as needed). Add `"apps.<name>"` to `INSTALLED_APPS` in `config/settings/base.py`. Include in `config/urls.py` as `path("api/<name>/", include("apps.<name>.urls"))`. WebSocket consumers go in `consumers.py`; register routes in `config/routing.py`.

**Realtime channels (WS)** — three conventions documented in the design spec §3.3:
- `user.<id>.notifications` — trigger fires, observer completions, errors
- `thread.<id>` — streaming AI tokens, message lifecycle
- `snapshot.<id>` — per-section capture progress

Each is a Channels group. Groups are joined in `connect()` and left in `disconnect()`. See `apps/core/consumers.py` for the minimal reference consumer.

**Provider abstraction:** `apps/ai/providers/base.py` defines the `Provider` protocol; implementations are `ClaudeProvider` (anthropic SDK), `OpenAIProvider`, and `LocalProvider` (openai SDK to user-configured base URL). `run()` emits a normalized event union (`text_delta | image_ref | usage | done | error`) so the WebSocket consumer is provider-agnostic. Selection flows through `apps/ai/router.py` (precedence rules) and `get_provider()` factory; do not instantiate providers directly from views/tasks. Cost calculation lives in `apps/ai/cost.py` against `apps/ai/catalog.py` (per-model pricing entries). See design spec §6.

**Multi-provider fan-out:** `POST /api/threads/<id>/compare` runs the same prompt across multiple provider+model pairs in parallel, streaming each into its own branch. Stopping a stream: `POST /api/threads/<id>/messages/<msg_id>/stop` — tasks must check the stop flag, see `apps/threads/tasks.py`.

**Capture pipeline:** `apps/snapshots/services.py` orchestrates per-section Celery subtasks (quotes, chain, OHLC, positions, breadth, news, charts), each idempotent with its own retry. Partial failures are acceptable; missing sections are explicitly marked in the AI payload. `apps/snapshots/token_budget.py` trims the payload before it hits the model. See design spec §5.

**Event-trigger evaluator (not yet implemented — M7):** A Celery beat-scheduled task (`evaluate_triggers`) runs every ~10s — NOT a long-running worker process and NOT a separate container. Condition DSL is JSON with top-level `all/any/not` and leaves like `{"metric", "ticker", "op", "value", "window"}`. See spec §4.8 and §7.2.

## Non-obvious conventions

- **Everything runs in Docker.** Pyright/mypy/eslint errors about missing modules when you view files in your editor are expected — deps only exist inside the containers. Run lint via `make lint` (which shells into the containers).
- **`beat` depends on `web` health.** In `compose.yaml`, beat's `depends_on` includes `web: condition: service_healthy`. Without this, `DatabaseScheduler` races `manage.py migrate` and crashes on an empty schema. Do not remove.
- **Makefile runs `mypy .` not `mypy backend`** because `WORKDIR` inside the `web` container is `/app/backend`. Outside the container (e.g., in CI) you run `mypy backend` from repo root — both invocations are correct for their cwd.
- **Tool config is duplicated.** `pyproject.toml` has `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]` AND standalone `ruff.toml` / `mypy.ini` / `pytest.ini` exist at repo root. The Dockerfile only copies `pyproject.toml`, so the container uses that; standalone files would be used by local (non-Docker) tool invocations. When editing config, update both for now until consolidation.
- **`uv.lock` is not committed.** Each fresh Docker build re-resolves dependencies via `uv sync --no-install-project --dev`. For reproducible builds, generate and commit the lockfile (`docker compose exec web uv lock` → copy back to host).
- **Worker container has chromium for Playwright.** Cold builds of the worker image are ~3–5min slower because of the chromium download (~150MB binary + ~13 Debian system libs). The `web` and `beat` services use the smaller default image without chromium.
- **Render route `/render/chart`** is deterministic — URL params fully specify the render. Used by `apps.snapshots.services.render.render_chart_png` to capture chart PNGs via headless chromium. In dev: `http://frontend:5173/render/chart?...`. In prod: hash-route on `index.html` so we can reach the SPA via Whitenoise without solving SPA-mode.
- **Image bytes live in Postgres** (`SnapshotImage.data` BinaryField), not on disk. `serve_image` view reads via `bytes(img.data)` because Django's BinaryField returns memoryview. `DATA_UPLOAD_MAX_MEMORY_SIZE` in settings is aligned with the 5MB image cap so oversized uploads produce a clean 413 instead of bare 400 from Django's body-buffer guard.
- **Prod `/` returns 404; SPA is at `/static/index.html`.** Known M1 carry-over. Either configure Whitenoise SPA mode or add a Django catch-all URL in a later milestone.
- **Single-user auth is a token written to `/data/user.token` on first boot.** No password UI. The container binds to `127.0.0.1` only.
- **URL include ordering matters.** `config/urls.py` registers specific prefixes (e.g., `/api/costs/`) *before* generic `/api/` includes — a past regression routed `/api/costs/today` into the wrong app. Don't reorder without checking.
- **Encrypted secrets at rest:** Schwab OAuth tokens, provider API keys, etc. live in `ProviderConfig` / `ApiCredential` rows, encrypted via `django-cryptography`. Key is derived from `DJANGO_SECRET_KEY` + `/data/secret.salt`. Do not log these fields; do not expose them via DRF serializers without explicit write_only.

## Testing

- **Unit** (pure logic): lots of these planned for condition evaluator, payload serializer, cost calc, market-hours, DSL parser, token estimator. Favor `pytest.mark.parametrize`.
- **Integration**: real Postgres via testcontainers (or CI services), `fakeredis`, Celery eager (`CELERY_TASK_ALWAYS_EAGER=True`). External APIs mocked at the SDK boundary with `respx` or `vcrpy`.
- **E2E**: `playwright-python` driving the full compose stack; one happy path per top-level route.
- **Frontend**: `vitest` + `@testing-library/react`. Do not duplicate E2E there.

Tests are expected to pass before commit. `make check` gates CI.

## Workflow

Planning work uses the superpowers skills (`brainstorming` → `writing-plans` → `subagent-driven-development`) and lands specs in `docs/superpowers/specs/` and plans in `docs/superpowers/plans/` (YYYY-MM-DD-<topic>.md). Each new milestone = new spec section pointer + new plan. Keep commits bite-sized and conventional (`feat(core):`, `fix(frontend):`, `chore:`, `docs:`, `ci:`, `feat(infra):`).

## Design references

- Full system design: `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`
- Milestone plans: `docs/superpowers/plans/` — M1 skeleton, M2 market data, M3 snapshots+AI, M4 threads (all shipped); M5 chains+news+images (active).
- M5 design addendum: `docs/superpowers/specs/2026-04-17-m5-chains-news-images-design.md`
- Milestone roadmap: design spec §16 (M1 skeleton → M2 market data → M3 snapshots+AI → M4 threads → M5 options/news/images → M6 observer → M7 triggers → M8 polish).
