# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-user desktop dashboard that captures snapshots of the stock market and routes them to a chosen AI (Claude / OpenAI / local OpenAI-compatible endpoint) for observations framed by a named trading style and per-snapshot objective. Strictly observational — no broker write path. Runs entirely in Docker Compose.

The design lives in `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`. Milestone plans live in `docs/superpowers/plans/`. Both are load-bearing — read the relevant spec section before adding a feature, and read the active milestone plan before starting new implementation work.

Milestones M1 (skeleton, tagged `m1-skeleton`) → M10 (AI platform v2.5, tagged `m10-ai-platform-v25`). Each has its own plan and is independently shippable. **Current status:** M1–M10 all shipped.

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
- **AI token counts are provider-aware.** `apps.ai.token_counter.estimate_tokens(text, provider=, model=)` routes Claude to Anthropic's `count_tokens` endpoint (cached via `lru_cache`) and everything else to `tiktoken.cl100k_base`. Call sites that don't pass provider/model get the old tiktoken default — intentional back-compat — but new code should pass them through.
- **Per-model payload budgets live in the catalog.** `ModelInfo.max_payload_tokens` (150k for Claude 4.x, 200-300k for GPT-5 variants). `serialize_for_ai` resolves the budget from `(provider, model)` when `max_tokens` isn't passed explicitly. Raising a model's budget here is the right place; hard-coding 40k is wrong.
- **Claude multi-turn runs cache the final prior message.** `RunRequest.cache_last_message=True` (set automatically when `len(messages) > 1` in `_build_request`) attaches a second `cache_control` breakpoint on the last message's final text block. On cache hit, Anthropic bills ~0.1× base input for everything before the breakpoint.
- **Monthly cost cap parity with daily cap.** `apps.ai.cost.check_monthly_cap(provider, cap_usd, prospective)` sums the last 30 days of `AIRun.cost_usd`. Null cap is a no-op (opt-in). Wired into `threads.tasks`, `observer.services.run`, and `triggers.tasks`.
- **Observer schedules have three opt-in modes.**
    - `structured=True` — route through `apps.ai.providers.claude_structured.run_structured` with the `ObservationReport` Pydantic schema; parsed result lands in `Message.content` as `{"kind": "structured_observation", "report": <json>}` for typed UI cards.
    - `mode="diff"` — feed AI only `apps.snapshots.diff.diff_sections(...)` delta vs the most recent prior ready snapshot (falls back to full payload if no prior).
    - `use_batch=True` — submit a Messages Batch (one `custom_id` per watchlist ticker). `observer.poll_open_batches` beat task (every 60s) moves completed batches into the observer thread. 50% cheaper; no streaming during the window.
  All three are orthogonal and default False.
- **Snapshot diff endpoint.** `GET /api/snapshots/<id>/diff/?against=<other_id>` returns `{delta: <markdown>, prev_id, curr_id}`. Not yet surfaced in the UI; power users can call it directly.
- **Trigger backtest.** `POST /api/triggers/backtest/` body `{condition, start, end, timeframe?}` replays the DSL over stored `OHLCBar` rows and returns match timestamps. Only `price` and `pct_change` leaves are evaluated; live-only metrics (vix, position_pl) are silently absent from per-bar snapshots rather than raising.
- **Frontend primitives.** `Skeleton` / `SkeletonRows` / `EmptyState` / `ErrorBoundary` / `Toasts` live in `frontend/src/components/`. Reach for these before writing ad-hoc loading spinners, "no data" text, or try/catch-in-JSX guards. Toasts require a `<ToastProvider>` ancestor; `AppLayout` already provides it.
- **Command palette is Cmd/Ctrl-K.** `useCommandPaletteTrigger(cb)` registers the global handler; default commands in `AppLayout`'s `useDefaultCommands()` cover all top-level routes. Page-level commands can be added by extending the hook.
- **Tool use on Claude is opt-in per profile.** `TradingProfile.enable_tools=True` causes `_build_request` to inject `apps.ai.tools.registry.default_toolset().anthropic_tools()` into `RunRequest.tools`. The provider loops on `stop_reason == "tool_use"`, dispatching each tool_use block through `Toolset.run(name, input)`, streaming back a `tool_result` turn, and repeating. Every call produces a `ToolCall` row on the assistant `Message` and is broadcast over `thread.<id>` as `tool_call` / `tool_result`. Add a new tool by registering a `ToolSpec` in `apps/ai/tools/registry.py`.
- **Extended thinking is opt-in per profile.** `Profile.enable_thinking=True` + `Profile.thinking_budget=N` causes the provider to pass `thinking={type:enabled, budget_tokens:N}` on each iteration. Thinking chunks emit `thinking_delta` WS events. Billed as output tokens.
- **Per-profile Memory lives under `/data/memory/<profile_id>/`.** `Profile.enable_memory=True` attaches the `memory_20250818` tool with the per-profile directory, routed through `self._client.beta.messages.stream(...)` with the `context-management-2025-06-27` beta header. Override the root via `AI_MEMORY_ROOT` in tests.
- **Anthropic Files API** — `apps.files.UserFile` proxies an `anthropic_id` + metadata. `POST /api/files/` uploads through `anthropic.beta.files.upload`; `POST /api/threads/<id>/attach-file/` creates a user `Message` with `content={"blocks": [{"type":"document","source":{"type":"file","file_id":...}}, {"type":"text","text":...}]}`. The provider hands block lists to the SDK verbatim. Deleting a `UserFile` also calls `anthropic.beta.files.delete`; bytes do not live locally.
- **Citations on news** — `apps.ai.citations.news_to_search_result_blocks(items)` serializes news items as Anthropic `search_result` blocks with `citations: {enabled: true}`. The frontend `<Citation/>` component resolves citations back to `news://<id>` or the original URL.
- **`ChatMessage.content` is `str | list[dict]`.** Messages with a `"blocks"` key in `Message.content` thread through as content-block lists; otherwise as plain text. This is how files / images / citations / tool_result blocks co-exist with text.
- **Only `apps/ai/providers/claude.py` is M10-aware.** OpenAI / Local providers ignore `tools`, `thinking_budget`, `memory_dir`. Enabling these on a profile whose `default_provider != "claude"` is a silent no-op, not an error — parity is a future milestone.
- **Analytics are on-demand, never scheduled.** `apps.analytics` has five services — `leaderboard`, `cpi`, `trigger_heatmap`, `observer_timeline`, `unusual_options` — each backed by a single DRF view under `/api/analytics/`. They aggregate off indexed columns (`AIRun.created_at`, `TriggerFiring.fired_at`, `Message.created_at`, `OptionChainSnapshot.fetched_at`) at request time. No Celery tasks, no materialized views.
- **Provider leaderboard uses stored OHLC.** `provider_leaderboard(forward_hours=N)` correlates each AIRun against the snapshot's primary ticker (first `quotes` key) and the `OHLCBar` rows at capture vs capture+N hours. Runs without a snapshot, without a `quotes` section, or without price history show `coverage_pct=0` and `avg_forward_return_pct=None` — honest about what the data supports rather than inventing a number.
- **Unusual-options detector operates on `OptionChainSnapshot`.** Flags lines with `volume/oi >= 3.0` or `iv_z >= 1.5 sigma` over the 30-day chain-history mean IV for the ticker. Returns per-line `triggers` list so the UI can show WHY each line was flagged; not a scanner — a *reasoning* surface.
- **Observer timeline reads Messages, not a run log.** There is no dedicated `ObserverRun` table; the observer writes one Message per fire (assistant/done = success, assistant/failed = failure, system/done = cost-cap skip). The analytics service groups those by day.
- **AnalyticsPage route is `/analytics`** (keyboard shortcut `g a`, Cmd-K palette `go-analytics`). Cards are each self-contained and call one of the `useAnalytics.ts` hooks — `useLeaderboard`, `useCostPerInsight`, `useTriggerHeatmap`, `useObserverTimeline`, `useUnusualOptions(ticker)`.

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
