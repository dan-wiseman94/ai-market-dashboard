# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## What this is

A single-user desktop dashboard that captures stock-market snapshots and routes them to a chosen AI (Claude / OpenAI / local OpenAI-compatible endpoint) for observations framed by a named trading style and per-snapshot objective. Strictly observational — no broker write path. Runs entirely in Docker Compose.

Design: `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`. Milestone plans: `docs/superpowers/plans/`. **Both are load-bearing — read the relevant spec section before adding a feature.** M1→M15 shipped (M15 specs under `docs/superpowers/specs/2026-06-01-m15-*`); several features ship untagged (free data sources, prediction ledger, morning briefing, scorecard, semantic recall).

## Daily commands

Everything runs in Docker; Make targets wrap Compose.

| Command | What it does |
|---|---|
| `make dev` | Whole stack, `compose up --watch` (hot reload). First run 3–8 min. |
| `make shell` | Bash in `web` (ad-hoc `manage.py`). |
| `make migrate` / `make makemigrations` | Migrations inside `web`. |
| `make test` | `pytest` (web) + `vitest --run` (frontend). |
| `make lint` | Backend `ruff` + `ty` (advisory) + `lint-imports` + `typecheck` (mypy, zero-baseline) + `deptry` + `semgrep-rules`; frontend `pnpm run lint` + `depcruise` + `type-coverage`. |
| `make check` | `lint` + `test` (CI runs tests `-p no:randomly`). |
| `make check-migrations` | Fail if a model changed without a migration. |
| `make schema` | Regenerate `backend/schema.yml` (OpenAPI). FE types: `pnpm gen:api`. |
| `make e2e-schemathesis` | Fuzz every endpoint for 5xx (under `MOCK_EXTERNAL`). |
| `make mutate` | Mutation-test money paths (slow, nightly). |
| `make logs s=<svc>` | Tail a service (`web`/`worker`/`beat`/`redis`/`db`/`frontend`). |
| `make down` | Stop+remove containers (volumes kept). |
| `make prod` | Prod overlay — FE baked in, served by Whitenoise on `:8000`. |
| `make e2e` | E2E stack (`MOCK_EXTERNAL=true`), run `ui/api/ws/visual/a11y` lanes, tear down. Perf separate (`make e2e-perf`). |
| `make e2e-one t=<lane/mod.py>` | One e2e file; needs overlay up (`make e2e-up`). `HEADED=1` to debug. |
| `make e2e-visual-update` | Regenerate visual baselines, then `git diff`. |
| `make restore file=<name>` | Restore DB from `/data/backups/<name>`. |

One backend test: `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (container WORKDIR is `/app/backend` — drop the `backend/` prefix).
One FE test: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`.
Fresh rebuild (catches reproducibility bugs): `docker compose down -v && docker compose build --no-cache && docker compose up -d`.

## Architecture big picture

**Six-service compose stack** (dev): `web` (Django+DRF+Channels/Daphne), `worker` (Celery), `beat` (Celery beat, `DatabaseScheduler`), `redis` (broker+Channels layer+cache), `db` (Postgres 17), `frontend` (Vite). All bind `127.0.0.1` only.

**Django project** `backend/config/`, settings `base.py`/`dev.py`/`prod.py`. Apps `backend/apps/<name>/`, imported `apps.<name>` (PYTHONPATH `/app/backend`). Celery app `config.celery`, re-exported from `config/__init__.py`. Channels routing `config.routing`, mounted by `config.asgi`. **Celery task packages are listed explicitly in `config/celery.py` (`TASK_PACKAGES`, not autodiscovered)** — add new task modules there. Every scheduled task is also inventoried in `apps/core/scheduled_tasks.py` (drift-gated) and asserted registered by `apps/core/tests/test_celery_registration.py`.

**App roster** (`backend/apps/` — 15 apps):
- `core` — health, base consumer, logging, `MOCK_EXTERNAL`, `SystemSettings`+`runtime_config()`; shared abstract bases in `model_bases.py` (`Resolution`/`DirectionalCall`/`TimeStamped` + idempotent `claim()`); drift-gated inventories `feature_flags.py`/`scheduled_tasks.py`.
- `market` — Schwab client + free fallback providers (`services/`, orchestrated by `services/fallback.py`); quotes/OHLC/chain/news/macro/filings/treasury models; `returns.py` forward-return helpers.
- `snapshots` — capture services + token budget, `stamp_payload_tokens`; `SnapshotImage` bytes offloaded to `/data`.
- `ai` — providers, router, catalog, cost calc; cost aggregation/caps/CSV in `cost_reporting.py`/`cost_views.py` (`/api/costs/`; the `AIRun` model lives in `threads`).
- `threads` — `Message`+`AIRun`, consumer, compare endpoint, Decision Coach `coach.py`; `UserFile` Files-API proxy (`files_*.py`).
- `profiles` — trading-style profiles + `AgentPreset` (four seeded builtins).
- `secrets` — encrypted creds + Schwab OAuth + data-source keys; guarded accessor `credentials.py::decrypt_token`. Mounted at `/api/schwab/`.
- `observer` — automated monitoring: schedules+notifications+timeline; Prediction Ledger `AIPrediction` (`observer/predictions/`); trigger evaluator+DSL+firings (`observer/triggers/`); Morning Briefing (`observer/briefing/`).
- `backups` — pg_dump task + rotation + ViewSet.
- `export` — async zip bundles.
- `thesis` — theses + post-mortems + decision journal (`/api/theses/`, `/api/journal/`); `Position` (`/portfolio`); `Lesson` (feeds Coach; `thesis.distill` beat).
- `analytics` — on-demand aggregations; `GET /api/dashboard/` rollup; eval/calibration harness `EvalRun`.
- `recall` — semantic+keyword search (pgvector) feeding the Coach.
- `book` — daily whole-book risk reading; append-only `BookSnapshot`; `book.snapshot_daily` beat.
- `strategy` — M15 Strategist subpackages: `coverage/` (living per-ticker house view), `warroom/` (multi-agent debate streaming over `thread.<id>`), `desk/` (anomaly sweep), `regime/` (append-only readings, latest=current).

**Consolidation merge-map (27→15, 2026-06).** Only modules moved — **every `/api/<x>/` route is unchanged**. Absorbed: `costs`→`ai`; `dashboard`,`aieval`→`analytics`; `files`→`threads`; `portfolio`,`lessons`→`thesis`; `predictions`,`triggers`,`briefing`→`observer`; `coverage`,`warroom`,`desk`,`regime`→ new `strategy`. **Beat tasks renamed to their owning app** (the `test_celery_registration` prefix guard): e.g. `aieval.run_scheduled`→`analytics.aieval_run_scheduled`, `briefing.run_scheduled`→`observer.briefing_run_scheduled`, `regime.refresh`→`strategy.regime_refresh`, `desk.sweep`→`strategy.sweep`, `lessons.distill`→`thesis.distill`. **Queued/DB-seeded tasks kept their names** (no beat-guard): `triggers.evaluate_triggers`/`fire_trigger`, `coverage.revise_from_observation`, `warroom.run_debate`. **Inbound-FK clusters must move as a unit** — a kept app's migration depending on a removed app dangles the graph (so `coverage`+`warroom`+`desk`→`strategy` moved together). Each moved table preserves `db_table` (`SeparateDatabaseAndState` for ORM state + `RunPython` create-if-missing).

**Adding a Django app:** use the `new-django-app` skill. Wiring: `AppConfig` with `name="apps.<name>"` + short `label`; add to `INSTALLED_APPS` (`config/settings/base.py`); include in `config/urls.py` **before** the generic `/api/` include; consumers in `consumers.py`, routes in `config/routing.py`.

**Realtime channels (WS)** — Channels groups joined in `connect()`, left in `disconnect()` (ref: `apps/core/consumers.py`):
- `user.<id>.notifications` — trigger fires, observer completions, backup/export, errors.
- `thread.<id>` — streaming tokens + lifecycle (`message_started`/`text_delta`/`message_done`/`cost`/`error`). `cost` follows `message_done`, carries `parent_message_id` for Compare branch routing.
- `snapshot.<id>` — per-section capture progress.

**`thread.<id>` reconnect replay buffer** — `apps/threads/event_log.py` stamps each event a monotonic `seq` (Redis INCR), keeps the last 256 (capped list, 1h TTL); `ThreadConsumer.connect()` replays `seq > since` when `?since=` present. `WebSocketProvider.tsx` sends `?since=` only **on reconnect** (a tracked seq IS the reconnect signal). Seq-less channels never replay.

**Provider abstraction** — `apps/ai/providers/base.py` `Provider` protocol; `ClaudeProvider`/`OpenAIProvider`/`LocalProvider`. `run()` emits a normalized event union so the consumer is provider-agnostic. **Selection flows through `apps/ai/router.py` + `get_provider()` — do not instantiate providers directly from views/tasks.** Cost calc in `apps/ai/cost.py` against `catalog.py`.

**Multi-provider fan-out** — `POST /api/threads/<id>/compare` runs one prompt across provider+model pairs in parallel, each its own branch. Stop: `POST .../messages/<id>/stop` sets a Redis flag (`stop.py`); the streaming loop polls it (~0.25s) and `gen.aclose()`s the provider, halting generation+billing.

**Capture pipeline** — `apps/snapshots/services/` fills sections in one `snapshots.capture` task as a **synchronous loop** over `snap.includes` (quotes/chain/ohlc/positions/breadth/news/image + opt-in macro/filings/treasury/events/overnight; market fetchers fall back to free providers). A raising section is caught + marked `failed` (no retry, `error` scrubbed of key-bearing URLs); partial failures are OK and marked in the payload. The 24h 1m OHLC window keeps only the newest ~4h at 1m (older 5m — a 23h futures session or premarket capture would otherwise ship ~1,000 bars); chain uses the first non-futures watchlist symbol (Schwab chains 400 on futures). The `ohlc` section also carries `watchlist_daily` — per-watchlist-ticker daily history (≤8 tickers × 60 bars, best-effort per ticker) so cross-name objectives (breakout scans) are answerable. Before the model, the serializer drops `watchlist_daily` under token pressure, then truncates oversized OHLC to its newest bars, then `token_budget.py` drops whole sections (`chain→ohlc→news→…`). Cash indices ($SPX, $TNX) report volume 0 on every bar — the serializer omits the volume column with a note (zeros read as a broken feed to the AI). The `macro` section pairs FRED series (H.15 publishes ~1 business day behind — lag is source-inherent, noted in the render) with live CBOE yield-index quotes (`market/services/yields.py`; indices quote yield×10). (Spec §5 says a Celery chord; real impl is this loop — prefer it.)

**Event-trigger evaluator** — beat task `evaluate_triggers` every ~10s (NOT a long-running process/container). DSL is JSON: top-level `all/any/not` + leaves `{metric,ticker,op,value,window}`. Spec §4.8, §7.2.

**Frontend routing** — all routes nest under `<AppLayout>` (TopNav+SideNav+NotificationBell+ConnectionStatusDot+Breadcrumbs); only `/render/chart` bypasses it. Add routes as children in `frontend/src/router.tsx` with `handle: { crumb: "..." }`. Shortcuts are `g <x>` (`useKeyboardShortcuts.ts`).

## Non-obvious conventions

**Landmines** (silent failures) are the highest-value entries — preserve them when editing.

### Docker, tooling & tests
- **Editor errors about missing modules are expected** (everything runs in Docker); lint via `make lint`.
- **`beat` depends on `web` health** in `compose.yaml` — else `DatabaseScheduler` races `migrate` and crashes on an empty schema. Don't remove.
- **`ty` is advisory** (CI `continue-on-error`; ~900 false-positive Django diagnostics). Real gates: `ruff` + `pytest` + FE `eslint`/`tsc` + `vitest`.
- **All tool config is in `pyproject.toml`**; no `ruff.toml`/`pytest.ini`. **`uv.lock` is committed** (`uv sync --frozen`); regenerate with `uv lock` on host.
- **Only `web`/`frontend` hot-reload.** After adding/renaming a task module or `beat_schedule` entry, `docker compose restart worker beat` or it won't fire (fresh `up`/CI unaffected).
- **Worker image carries chromium** (Playwright; slower cold builds); the render test passes only from `worker`. `web`/`beat` use the smaller image. **Integration tests excluded by default** (`-m 'not integration'`).
- **`MOCK_EXTERNAL=true`** (set by `compose.e2e.yaml`) short-circuits Claude/OpenAI/Local/Schwab/Finnhub to fixtures. **Never set it on the dev stack** — provider unit tests patch the SDK client class directly (e.g. `patch("apps.ai.providers.claude.AsyncAnthropic", ...)`) and that patch sits *below* the `is_mock_mode()` short-circuit, so a stray `MOCK_EXTERNAL=true` makes them silently exercise canned fixture streams instead. If you see "Mocked response" in dev, recreate containers (`docker compose stop web worker beat && rm -f … && up -d`).

### Backend wiring & security
- **URL include order** — `config/urls.py` registers specific prefixes (e.g. `/api/costs/`) **before** generic `/api/`. Don't reorder.
- **DRF exposes FK ids as `*_id`, not nested objects** — FE TS must use `thread_id` etc. verbatim (`thread` reads `undefined`).
- **Security is network isolation, not auth.** Binds `127.0.0.1`; DRF defaults `AllowAny`, no user token; WS is Origin-validated. **Do not bind `0.0.0.0` without adding real auth first.**
- **Encrypted secrets at rest** — Schwab/provider keys in `ProviderConfig`/`ApiCredential` (django-cryptography). Don't log them or expose without `write_only`. **All reads go through `apps/secrets/credentials.py::decrypt_token`** (degrades to skip on undecryptable token). Keep the `ApiCredential` import location — moving it breaks `<module>.ApiCredential` patch sites.
- **Prod `/` serves the SPA** (Whitenoise `WHITENOISE_INDEX_FILE` + `TemplateView` catch-all excluding `api/|static/|render/|ws/|admin/`).

### Snapshots, images & rendering
- **Section terminal state is `"done"`; only the parent `Snapshot` uses `"ready"`.** Mixing them silently drops images (`_snapshot_image_ids()` filters `status="done"`).
- **Pinned snapshots reach the LLM as a synthetic first user turn** — `ThreadViewSet.create()` synthesizes a `done` user `Message` (`content["text"]=serialize_for_ai(snap)`, `snapshot_ref=snap`); observer/trigger paths do the same per fire. **Do not load the snapshot inside `_build_request()`** (the synthetic-message pattern keeps the pipeline provider-agnostic + UI-visible). Images attach separately via `_snapshot_image_ids()`.
- **Snapshot image bytes are offloaded to `/data`** (new rows: `file_path`, `data` NULL; legacy: in-DB). **Always read via `apps.snapshots.image_store.read_image_bytes(img)`, not `bytes(img.data)`.** Captures go through `image_store.create_image` (volume-write failure degrades to in-DB). `DATA_UPLOAD_MAX_MEMORY_SIZE` aligns with the 5MB cap → clean 413.
- **`/render/chart` is deterministic** — URL params fully specify the render; `render_chart_png` captures via headless chromium.
- **Snapshot diff** — `GET /api/snapshots/<id>/diff/?against=<id>` → `{delta, prev_id, curr_id}`.
- **`ChatMessage.content` is `str | list[dict]`** — a `"blocks"` key threads through as a content-block list, else plain text.

### AI providers & capabilities
- **Tool use has provider parity; thinking/memory/files/citations/structured-output are Claude-only.** OpenAI/Local run tools via a tool-call loop emitting the same events. Tools opt-in per profile (`enable_tools`); OpenAI/Local also gated on `ProviderConfig.supports_tools`. **Enabling a Claude-only feature elsewhere warns-and-continues** — `run_ai_on_message` calls `capabilities.unsupported_features(...)`, writes a `capability_warning` message + `warning` WS event (excluded from `observer_timeline`).
- **Add a tool** by registering a `ToolSpec` in `apps/ai/tools/registry.py` (writes a `ToolCall` row, broadcasts `tool_call`/`tool_result`).
- **Files API** — `apps.threads.UserFile` proxies `anthropic_id`; deleting also deletes upstream; bytes don't live locally.
- **News citations** — `apps.ai.citations.news_to_search_result_blocks(items)` → `search_result` blocks; FE `<Citation/>` resolves to `news://<id>`.
- **Multi-turn Claude caches the final prior message** (`RunRequest.cache_last_message`, auto when >1 message).
- **Investigate mode** — `run_ai_on_message(investigate=True)` forces tools on for a bounded loop under `AI_AUTONOMOUS_DAILY_CAP_USD`; opt-in via `EventTrigger`/`ObserverSchedule.investigate`; output `kind="investigation"`.

### AI tokens, cost, caps & routing
- **Token counts are provider-aware** — `token_counter.estimate_tokens(text, provider=, model=)` (Claude → Anthropic count_tokens; else tiktoken). New code should pass provider/model.
- **Per-model payload budgets live in the catalog** (`ModelInfo.max_payload_tokens`). `serialize_for_ai` resolves it from `(provider, model)` — **don't hard-code 40k.**
- **Cost caps** — `cost.check_monthly_cap(...)` sums 30d of `AIRun.cost_usd`; null cap = no-op. Wired into `threads.tasks`, `observer.services.run`, `triggers.tasks`. Local cost is $0 (caps/meters hidden in UI).
- **Cross-provider failover** (opt-in `AI_FAILOVER_ENABLED`) — retry once on a secondary only if the primary errors **before emitting any token** (gated on empty buffer); never after a token streamed (would duplicate).
- **Calibration-weighted routing** (opt-in `AI_CALIBRATION_ROUTING_ENABLED`) — router fallback tier picks the best-measured `(provider, model)` from recent `EvalRun`s; query `.defer("_api_key")`s the encrypted column (else key rotation crashes routing).

### Observer, triggers & scheduling
- **Observer schedules drive beat via `OneToOneField(PeriodicTask)`** — ViewSet calls `sync_periodic_task(...)` explicitly (no signals). Cron evaluates in `OBSERVER_BEAT_TIMEZONE` (default UTC; set `America/New_York` for ET presets).
- **Observer opt-in modes** (all default False): `structured` (→ `run_structured` `ObservationReport`), `mode="diff"` (only delta vs prior ready snapshot), `use_batch` (Messages Batch, 50% cheaper, no streaming; `poll_open_batches` every 60s), `consensus` (with structured: cross-model agreement), `investigate` (plain mode only).
- **Observer response cache** (opt-in `OBSERVER_RESPONSE_CACHE_ENABLED`) — a plain fire with a byte-identical assembled prompt within TTL reuses the observation (`kind=cached_observation`). Plain path only.
- **Trigger backtest** — `POST /api/triggers/backtest/` replays the DSL over `OHLCBar`. Only `price`/`pct_change` leaves evaluate; live-only metrics silently absent (not raising).
- **NYSE market-hours** via `pandas-market-calendars` (`apps.market.calendar` — `registry.get_market_calendar` memoizes with `functools.cache` on first call; `apps.observer.services.market_hours` is a thin convenience wrapper over it, not the implementation).
- **Market events are a forward calendar, not a session calendar** — `apps.market.MarketEvent` (earnings+macro from Finnhub) ≠ `apps.market.calendar` (sessions). Reads go through `events.upcoming_events(...)`. Macro degrades to `SEED_MACRO_EVENTS` — **and in practice the seed IS the macro source** (Finnhub's economic calendar is premium; free keys 403), so refresh `events_seed.py` before its dates lapse or every snapshot/briefing silently shows `macro: []` (`fetch_macro` warns when nothing upcoming remains).
- **Only equity-like symbols reach Finnhub company endpoints + EDGAR** — gate with `symbols.is_equity_like` (bare futures roots collide with unrelated equities there: "ES" is Eversource to Finnhub while the rest of the app treats it as /ES; indices/futures aren't SEC filers). Provider errors embed the key-bearing request URL — log via `safe_log.safe_err`, and anything user-facing goes through `safe_log.scrub_secret_params` (the capture loop scrubs `section.error`).

### Thesis, post-mortems & calibration
- **Pre-trade discipline on thesis create** — `ThesisSerializer.validate` requires non-empty `rationale` AND an invalidation (`invalidation_price` OR `invalidation_note`), **create only** (edits/ORM/fixtures bypass).
- **Post-mortem objective verdict is deterministic — no AI key needed** — `postmortem.objective_verdict(thesis, fwd_pct)` (off `OHLCBar`, DEADZONE 1%). The Claude narrative layers on top and degrades silently to `report={}`; never raises out of `run_postmortem`.
- **Idempotent `scheduled→running` claim prevents double-billing** — `run_postmortem` opens with `filter(status="scheduled").update(status="running")`; 0 rows → exit. `THESIS_POSTMORTEM_HORIZONS=[7,30,90]`; `run_due_postmortems` every 300s.
- **Eval calibration loop is look-ahead-safe** — replays a candidate against **frozen** source snapshots of decisive theses. **Feed the model ONLY `serialize_for_ai(snapshot)`, never the coach/recall** (a coach block leaks post-trade info). Persists as `EvalRun`. Scheduled beat opt-in/OFF (`AIEVAL_SCHEDULED_ENABLED`) — `run_structured` has no `MOCK_EXTERNAL` short-circuit, so an always-on schedule hits the real model.
- **`DecisionJournalEntry` lives in `apps.thesis`, not `apps.threads`** (avoids a `threads→thesis` import cycle). `/api/journal/?thread=<id>`.
- **`get_or_create_review_thread(thesis)` uses `kind="consult"`** — one review thread per thesis via `Thesis.review_thread` FK.
- **`apps/market/returns.py` is the shared price-path helper** — both analytics and post-mortems import from there; don't inline.
- **`AgentPreset` builtins are seeded by a data migration**; `builtin` is read-only; duplicate slug → 400. **pytest-django `serialized_rollback` does NOT restore data-migration-seeded rows under `--reuse-db`** — a `transaction=True` test wipes the seeded builtins, so `apps/profiles/tests/conftest.py` re-seeds them via an autouse fixture; mirror that for any migration-seeded table.

### Analytics, Coach & scorecards
- **Analytics are on-demand, never scheduled** — DRF views under `/api/analytics/` aggregating off indexed columns at request time. No Celery tasks/materialized views. (`cohort_base_rate` is Coach-internal, not an endpoint.)
- **Leaderboard uses stored OHLC** — correlates each `AIRun` against its snapshot's primary ticker + `OHLCBar` at capture vs capture+N. No price history → `coverage_pct=0`, `avg_forward_return_pct=None` (not invented).
- **Unusual-options** flags `OptionChainSnapshot` lines with `volume/oi ≥ 3.0` or `iv_z ≥ 1.5σ` (reasoning surface, not a scanner).
- **Observer timeline reads Messages, not a run log** — no `ObserverRun` table; one Message per fire (assistant/done=success, assistant/failed=failure, system/done=cost-cap skip).
- **Scorecard** (`/scorecard`, `g k`) — `calibration.py` aggregates `PostMortem ⋈ Thesis` (conviction calibration + Brier) + provider calibration. `?horizon=` (7/30/90, default 30). `mixed` counts; `inconclusive` filtered. Buckets drill down (counts reconcile).
- **The Coach** (`assemble_coach_context`, `coach.py`) injects calibration + cohort base-rate + distilled-lessons blocks. **All read decisive completed post-mortems only (look-ahead-safe)** and degrade via `_safe()`. Lessons clustered by embedding cosine similarity in the `thesis.distill` beat.
- **The Mirror** (`/mirror`, `trader_calibration.py`) — self-calibration signals, **hard-gated on min-n** ("insufficient history", not a verdict).
- **AnalyticsPage** is `/analytics` (`g a`); cards each call a `useAnalytics.ts` hook.

### Data sources, predictions & coverage
- **Free data sources + graceful fallback** — `apps/market/services/` ships keyed/keyless clients; `services/fallback.py` routes quotes/OHLC/chain/news to a free provider when Schwab isn't connected. Keys are `ApiCredential` rows at `/api/schwab/data-sources/…` backed per-field by `DATA_SOURCE_ENV_KEYS` env vars (`FINNHUB_API_KEY`, …; DB wins); all reads via `decrypt_token`. **UI-saved keys die with the Docker volumes** — `docker compose down -v` removes the credential rows AND the `/data` Fernet salt (either loss alone destroys them; `decrypt_token` degrades to the env fallback, so the UI just shows "Not connected"). Env-backed keys survive rebuilds; tests get `DATA_SOURCE_ENV_KEYS={}` via a `backend/conftest.py` autouse fixture so a developer's real keys can't flip "not configured" assertions.
- **Prediction Ledger** — `apps.observer.AIPrediction` is the AI's directional call, **auto-extracted** from a structured `ObservationReport` by `observer/predictions/services/extract.py` (zero added cost; `None` never breaks the fire). Dedup: ≤1 `open` per `(ticker, horizon, profile)` — a same-direction re-fire is a no-op (call stays frozen for honest calibration), a flip invalidates+reopens. Beat (300s): `observer.resolve_due_predictions` + `observer.check_prediction_invalidations`.
- **COVERAGE — living per-ticker house view** — `apps.strategy.CoverageNote` revised **with a reason** by `strategy/coverage/services/revise.py` behind a **hysteresis gate** (writes a `CoverageRevision` only on created OR material_change OR stance/conviction delta; else reaffirm, no churn). Best-effort, `None` on no-key/cap/error. Observer auto-revises **by existence** (`hooks.py::maybe_revise_from_snapshot` queues only if the primary ticker already has a note). `CoverageRevision.source_snapshot` is `SET_NULL`. **Gotcha:** a broad `coverage/` line in `.gitignore` swallowed `backend/apps/strategy/coverage/`; a `!backend/apps/strategy/coverage/` negation keeps it tracked (relocate it when moving the app). Any new app/dir colliding with a common ignore pattern hits this.

### Frontend & runtime config
- **Frontend primitives** — reach for `Skeleton`/`SkeletonRows`/`EmptyState`/`ErrorBoundary`/`Toasts` before ad-hoc spinners/text/try-catch. Toasts need a `<ToastProvider>` (AppLayout provides one).
- **Command palette is Cmd/Ctrl-K** — `useCommandPaletteTrigger(cb)`; defaults in `useDefaultCommands()`.
- **Notifications are user-anonymous in v1** — `Notification.user` nullable; consumer on `user.anonymous.notifications`. Switch to `user.<id>.notifications` when auth lands. **`Notification.kind` is `varchar(16)`** (`apps/observer/models.py`) — a kind string >16 chars silently overflows at write time; keep new kinds ≤16 (`cal_drift`/`contra`, not `calibration_drift`).
- **Watchlist "what changed"** — per-ticker expander lazily fetches the latest snapshot diff (only when expanded).
- **UI-configurable runtime settings** — `apps.core.SystemSettings` (singleton `.load()`, `pk=1`); `runtime_config()` resolves `SystemSettings.<field> ?? settings.<DEFAULT>` (no restart). **Sync-context knobs only** (retention windows, AI failover, observer response cache, scheduled-eval); the async-ORM boundary keeps per-stream knobs env-only. `GET/PATCH /api/settings/` (PATCH `null` clears).
- **Local provider needs `host.docker.internal`** (mapped in `compose.yaml`) **+ lists its own models** — `POST /api/schwab/providers/<p>/probe/` calls `list_models()` and persists `discovered_models`. **Do not add SSRF private-IP filtering to the probe** — local endpoints are on localhost/private addresses by design.
- **Dashboard rollup is fault-isolated per section** — `GET /api/dashboard/` returns five sections each wrapped by `_safe(fn, default)`. **Defaults MUST be full contract-valid shapes** (e.g. `{"armed_count":0,"latest_firings":[]}`, not `{}`) — a `{}` default crashes the SPA tile that reads `latest_firings.length`.
- **Morning Briefing** (`apps.observer.briefing`) — `BriefingConfig` (singleton) + `BriefingRun`; `assemble.py` gathers deterministic sections (each wrapped so it never raises), `run.py` posts a synthetic user `Message` into a `kind="briefing"` thread for best-effort AI synthesis. `observer.briefing_run_scheduled` (15 min) fires once/day via a unique `scheduled_date` claim (manual `POST /api/briefings/run/` is unlimited). Data sections render with no AI key.

## Testing

- **Unit** (pure logic): condition evaluator, payload serializer, cost calc, market-hours, DSL parser, token estimator. Favor `parametrize`.
- **Integration**: real Postgres (testcontainers/CI services), `fakeredis`, Celery eager. External APIs mocked at the SDK boundary via `unittest.mock.patch` on the SDK client class (e.g. `AsyncAnthropic`, `AsyncOpenAI`), not `respx`/`vcrpy`.
- **E2E**: six lanes under `e2e/` on the full stack (`MOCK_EXTERNAL=true`) — `ui`/`api`/`ws`/`visual`/`a11y`/`perf`. Design: `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md`.
- **Frontend**: `vitest` + `@testing-library/react`; don't duplicate E2E.

### Quality gates (CI) — landmines

`make lint`/`make check` run them (config in `.github/workflows/`, `pyproject.toml`, `semgrep.yml`). mypy is a real gate (zero baseline — legacy `mypy-baseline.txt` driven to 0 and removed; fails on any error); `ty` advisory. Supply-chain `pip-audit`/`pnpm audit` are **BLOCKING**.

- **Architecture contracts** (`import-linter` + FE `dependency-cruiser`) — concrete AI providers private to `apps.ai` (use `get_provider`/router); crypto (`apps.secrets.{fields,keys}`) private to `apps.secrets`; FE `src/api` must not import `src/{pages,components}`. A direct import elsewhere reds CI. (`depcruise` needs a glob, not a bare dir.)
- **OpenAPI contract** — `backend/schema.yml` + `frontend/src/api/schema.d.ts` are committed + drift-gated (source of the `*_id` contract); `schemathesis` fuzzes for 5xx under `MOCK_EXTERNAL`.
- **Coverage floors** — backend `fail_under=86` (branch coverage enabled), FE vitest 80/74/77/82; `type-coverage` FE `any`-ratchet (floor 99). Property tests (Hypothesis) cover DSL/token-budget/cost/market-hours; `gitleaks` scans staged + CI history; `mutmut` nightly (non-gate).
- **Semgrep landmine rules** (`tools/semgrep/rules/`) — CLAUDE.md silent-failures as executable rules (`bytes(img.data)`, `0.0.0.0` bind, `_safe(_, {})`, secret logging); image-bytes rule exempts `image_store.py`; `make semgrep-rules-test` validates fixtures. Plus the Semgrep registry (`semgrep ci`).
- **`deptry`** (gate) — **run after `uv sync`** (needs installed metadata to map `rest_framework`→`djangorestframework`); `uvx deptry` is noisy. **`vulture`**/**`knip`**/**`guarddog`**/**`trivy`** advisory.
- **`ruff C901`** complexity ≤15 (gate); **`ruff S`** (bandit, gate) — no hardcoded secrets/weak hashes/shipped `assert` (sha256 not sha1; real guards survive `python -O`; `S101/5/6` ignored in tests/e2e).
- **N+1 guards** — `django_assert_max_num_queries` pins budgets (`apps/analytics/tests/test_*_query_budget.py`). Add one per new bounded aggregation.
- **Security SAST** — CodeQL (`security-extended`, auto-enabled on this public repo); hadolint (Dockerfiles digest-pinned); FE XSS lint (`no-unsanitized` + no `dangerouslySetInnerHTML`); migration-safety (squawk, paths-filtered to migration PRs).
- **Prompt-injection boundary** (code, not CI) — `coach.build_system_prompt` ALWAYS prepends a "data boundary" directive marking the user turn (snapshot/news/filings/tool output) as untrusted DATA, on every live run path (NOT the look-ahead-safe eval). **Don't drop it when refactoring.**
- **Determinism + flakes** — `pytest-randomly` runs locally/nightly, but the **per-commit gate runs `-p no:randomly`** (definition order). Tests use `config.settings.test`; `backend/conftest.py` autouse fixtures reset calendar cache + channel layers + set Hypothesis `deadline=None` — keep them. Streaming providers dispatch ORM-touching tools off the loop via `sync_to_async(thread_sensitive=True)` (`claude._dispatch_tool`, `openai.toolset.run`); **do NOT set `DJANGO_ALLOW_ASYNC_UNSAFE`** (corrupts the connection, cascades `OperationalError`; root-fixed in `7412bcd3`).
- **Inventory drift gates** — `apps/core/feature_flags.py` (every `env.bool` flag) + `apps/core/scheduled_tasks.py` (every `beat_schedule` task) are CI-gated against live code; add the registry entry in the *same* change or CI reds. The `.md` narratives aren't gated — keep in sync by hand.
- **Sentry** opt-in (`SENTRY_DSN` empty → no-op).

Tests must pass before commit. `make check` gates CI.

## Workflow

Planning uses the superpowers skills (`brainstorming` → `writing-plans` → `subagent-driven-development`); specs land in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/` (YYYY-MM-DD-<topic>.md). Commits bite-sized + conventional (`feat(core):`, `fix(frontend):`, `chore:`, `docs:`, `ci:`).

## Design references

- System design + roadmap (§16): `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`; milestone plans (M1→M15): `docs/superpowers/plans/`.
- Per-feature specs + milestone addenda: `docs/superpowers/specs/`. E2E + FE-coverage design: `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md`, `…-frontend-test-coverage-design.md`.
