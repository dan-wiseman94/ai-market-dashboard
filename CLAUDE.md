# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-user desktop dashboard that captures snapshots of the stock market and routes them to a chosen AI (Claude / OpenAI / local OpenAI-compatible endpoint) for observations framed by a named trading style and per-snapshot objective. Strictly observational — no broker write path. Runs entirely in Docker Compose.

The design lives in `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`. Milestone plans live in `docs/superpowers/plans/`. Both are load-bearing — read the relevant spec section before adding a feature, and read the active milestone plan before starting new implementation work.

Milestones M1 (skeleton, tagged `m1-skeleton`) → M8 (polish, tagged `m8-polish`). Each has its own plan and is independently shippable. **Current status:** M1–M8 all shipped; v1 feature set complete.

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
| `make e2e` | Start stack with `compose.e2e.yaml` overlay (`MOCK_EXTERNAL=true`), run `pytest e2e/`, tear down. |
| `make e2e-one t=<mod>` | Run one journey, e.g. `make e2e-one t=test_compare_flow`. Requires overlay up. |
| `make restore file=<name>` | Restore DB from `/data/backups/<name>`. Stops beat+worker, pg_restores, restarts. |

Run one backend test: `docker compose exec web pytest backend/apps/<app>/tests/test_<x>.py::<test_name> -v`

Run one frontend test: `docker compose exec frontend npx vitest run src/__tests__/App.test.tsx -t "specific test name"`

Full fresh-rebuild (wipes volumes, catches reproducibility bugs): `docker compose down -v && docker compose build --no-cache && docker compose up -d`

## Architecture big picture

**Six-service compose stack** (dev): `web` (Django + DRF + Channels via Daphne), `worker` (Celery), `beat` (Celery beat with `django_celery_beat.schedulers:DatabaseScheduler`), `redis` (broker + Channels layer + cache), `db` (Postgres 16), `frontend` (Vite dev server). Everything binds to `127.0.0.1` only.

**Django project** is `backend/config/` with settings split into `base.py` / `dev.py` / `prod.py`. Apps live under `backend/apps/<name>/` and are imported as `apps.<name>` (PYTHONPATH is `/app/backend` inside containers). Celery app lives at `config.celery` and is re-exported from `config/__init__.py` so `@shared_task` discovery works. Channels routing lives at `config.routing` and is mounted by `config.asgi`. Celery task packages are listed **explicitly** in `config/celery.py` (not autodiscovered) — a past silent-failure made autodiscovery untrustworthy; add new task modules to that list.

**App roster** (`backend/apps/`): `core` (health, base consumer, logging, `MOCK_EXTERNAL` flag), `market` (Schwab client, quotes/OHLC/chain/news models, cache), `snapshots` (capture services + token budget, `stamp_payload_tokens`), `ai` (providers, router, catalog, cost calc), `threads` (message model, consumer, compare endpoint, per-branch `cost` event), `costs` (per-provider + per-model + per-thread aggregation, daily/monthly caps, CSV export, snapshot drill-down), `profiles` (trading-style profiles), `secrets` (encrypted credential storage + Schwab OAuth; has `daily_cost_cap_usd` + `monthly_cost_cap_usd`), `observer` (schedules + notifications + timeline), `triggers` (evaluator + DSL + firings), `backups` (pg_dump task + rotation + DRF ViewSet), `export` (async zip bundles of threads/snapshots/observations/triggers/profiles/watchlists).

**Adding a Django app:** create `backend/apps/<name>/` with `__init__.py`, `apps.py` (`AppConfig` with `name = "apps.<name>"`, short `label`), `urls.py`, `views.py` (as needed). Add `"apps.<name>"` to `INSTALLED_APPS` in `config/settings/base.py`. Include in `config/urls.py` as `path("api/<name>/", include("apps.<name>.urls"))`. WebSocket consumers go in `consumers.py`; register routes in `config/routing.py`.

**Realtime channels (WS)** — three conventions documented in the design spec §3.3:
- `user.<id>.notifications` — trigger fires, observer completions, backup/export events, errors
- `thread.<id>` — streaming AI tokens, message lifecycle; carries `message_started` / `text_delta` / `message_done` / `cost` / `error` events. `cost` is emitted after `message_done` and carries `parent_message_id` so Compare UI can route it to the right branch tab.
- `snapshot.<id>` — per-section capture progress

Each is a Channels group. Groups are joined in `connect()` and left in `disconnect()`. See `apps/core/consumers.py` for the minimal reference consumer.

**Provider abstraction:** `apps/ai/providers/base.py` defines the `Provider` protocol; implementations are `ClaudeProvider` (anthropic SDK), `OpenAIProvider`, and `LocalProvider` (openai SDK to user-configured base URL). `run()` emits a normalized event union (`text_delta | image_ref | usage | done | error`) so the WebSocket consumer is provider-agnostic. Selection flows through `apps/ai/router.py` (precedence rules) and `get_provider()` factory; do not instantiate providers directly from views/tasks. Cost calculation lives in `apps/ai/cost.py` against `apps/ai/catalog.py` (per-model pricing entries). See design spec §6.

**Multi-provider fan-out:** `POST /api/threads/<id>/compare` runs the same prompt across multiple provider+model pairs in parallel, streaming each into its own branch. Stopping a stream: `POST /api/threads/<id>/messages/<msg_id>/stop` — tasks must check the stop flag, see `apps/threads/tasks.py`.

**Capture pipeline:** `apps/snapshots/services.py` orchestrates per-section Celery subtasks (quotes, chain, OHLC, positions, breadth, news, charts), each idempotent with its own retry. Partial failures are acceptable; missing sections are explicitly marked in the AI payload. `apps/snapshots/token_budget.py` trims the payload before it hits the model; `stamp_payload_tokens` records per-section token counts on `SnapshotSection.payload_tokens` for the cost drill-down. See design spec §5.

**Event-trigger evaluator:** A Celery beat-scheduled task (`evaluate_triggers`) runs every ~10s — NOT a long-running worker process and NOT a separate container. Condition DSL is JSON with top-level `all/any/not` and leaves like `{"metric", "ticker", "op", "value", "window"}`. See spec §4.8 and §7.2.

**Frontend routing:** All user-facing routes nest under a shared `<AppLayout>` (M8) — `TopNav` + `SideNav` + `NotificationBell` + `ConnectionStatusDot` + `Breadcrumbs`. Only `/render/chart` bypasses the layout. Add new routes as children of the parent route in `frontend/src/router.tsx` and give each a `handle: { crumb: "..." }` (string or function `({params}) => string`). Keyboard shortcuts are `g <x>` — see `frontend/src/hooks/useKeyboardShortcuts.ts`.

## Non-obvious conventions

- **Everything runs in Docker.** Pyright/mypy/eslint errors about missing modules when you view files in your editor are expected — deps only exist inside the containers. Run lint via `make lint` (which shells into the containers).
- **`beat` depends on `web` health.** In `compose.yaml`, beat's `depends_on` includes `web: condition: service_healthy`. Without this, `DatabaseScheduler` races `manage.py migrate` and crashes on an empty schema. Do not remove.
- **Makefile runs `mypy .` not `mypy backend`** because `WORKDIR` inside the `web` container is `/app/backend`. Outside the container (e.g., in CI) you run `mypy backend` from repo root — both invocations are correct for their cwd.
- **Tool config is duplicated.** `pyproject.toml` has `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]` AND standalone `ruff.toml` / `mypy.ini` / `pytest.ini` exist at repo root. The Dockerfile only copies `pyproject.toml`, so the container uses that; standalone files would be used by local (non-Docker) tool invocations. When editing config, update both for now until consolidation.
- **`uv.lock` is not committed.** Each fresh Docker build re-resolves dependencies via `uv sync --no-install-project --dev`. For reproducible builds, generate and commit the lockfile (`docker compose exec web uv lock` → copy back to host).
- **Worker container has chromium for Playwright.** Cold builds of the worker image are ~3–5min slower because of the chromium download (~150MB binary + ~13 Debian system libs). The `web` and `beat` services use the smaller default image without chromium.
- **Render route `/render/chart`** is deterministic — URL params fully specify the render. Used by `apps.snapshots.services.render.render_chart_png` to capture chart PNGs via headless chromium. In dev: `http://frontend:5173/render/chart?...`. In prod: hash-route on `index.html` so we can reach the SPA via Whitenoise without solving SPA-mode.
- **Image bytes live in Postgres** (`SnapshotImage.data` BinaryField), not on disk. `serve_image` view reads via `bytes(img.data)` because Django's BinaryField returns memoryview. `DATA_UPLOAD_MAX_MEMORY_SIZE` in settings is aligned with the 5MB image cap so oversized uploads produce a clean 413 instead of bare 400 from Django's body-buffer guard.
- **Observer schedules drive Celery beat via `OneToOneField(PeriodicTask)`.** `ObserverScheduleViewSet.perform_create` / `perform_update` call `sync_periodic_task(...)` explicitly — no Django signals. Beat picks up changes within its 5s sync interval. Cron expressions evaluate in `OBSERVER_BEAT_TIMEZONE` (default UTC; set to `America/New_York` for the UI's *ET cron presets to be correct year-round).
- **Pinned snapshots reach the LLM as a synthetic first user turn.** When a thread is created with `pinned_snapshot_id`, `ThreadViewSet.create()` synthesizes a `done` user `Message` whose `content["text"]` is `serialize_for_ai(snap)` and `snapshot_ref=snap`, inside a `transaction.atomic()` block with a status-ready guard. The existing `_build_request()` in `apps/threads/tasks.py` picks it up via the history query (`role__in=["user","assistant"], status="done"`). Observer/trigger paths use the same pattern per-fire (`apps/observer/services/run.py:72`). **Do not** load the snapshot inside `_build_request()` — the synthetic-message pattern keeps the AI pipeline provider-agnostic and gives the UI a visible record of what the model saw.
- **Notifications are user-anonymous in v1.** `Notification.user` is nullable; consumer subscribes to `user.anonymous.notifications`. When user-auth lands, switch to `user.<id>.notifications` everywhere. The bell mounts in the shared `<TopNav>` (M8).
- **NYSE market-hours check uses `pandas-market-calendars`.** Holiday + half-day correct; calendar cached at module import in `apps.observer.services.market_hours`.
- **Integration tests are excluded by default** via `addopts = "... -m 'not integration'"`. Run them explicitly with `pytest -m integration`. The Playwright render test only passes from the `worker` container (which has chromium); web doesn't. E2E journeys in `e2e/journeys/` also carry `@pytest.mark.integration` and run via `make e2e`.
- **Prod `/` now serves the SPA** via Whitenoise `WHITENOISE_INDEX_FILE = True` + a Django `TemplateView` catch-all in `config/urls.py` that excludes `api/|static/|render/|ws/|admin/`. Deep links work.
- **`MOCK_EXTERNAL=true`** is set by `compose.e2e.yaml` and causes `ClaudeProvider` / `OpenAIProvider` / `LocalProvider` / Schwab / Finnhub clients to short-circuit to canned fixtures (`apps.core.mocks`). Never set this env var on the normal dev stack — provider tests that use `respx` will hit the mock short-circuit instead and silently fail. If you see "Mocked response" in `test_claude_streams_text_and_usage`, run `docker compose stop web worker beat && docker compose rm -f web worker beat && docker compose up -d` to recreate containers without the overlay.
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
- Milestone plans: `docs/superpowers/plans/` — all shipped (M1 → M8).
- Milestone design addenda: `2026-04-17-m5-chains-news-images-design.md`, `2026-04-17-m6-observer-design.md`, `2026-04-18-m7-event-triggers-design.md`, `2026-04-18-m8-polish-design.md`.
- Milestone roadmap: design spec §16 (M1 skeleton → M2 market data → M3 snapshots+AI → M4 threads → M5 options/news/images → M6 observer → M7 triggers → M8 polish).
