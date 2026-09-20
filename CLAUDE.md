# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## What this is

A single-user desktop dashboard that captures stock-market snapshots and routes them to a chosen AI (Claude / OpenAI / local OpenAI-compatible endpoint) for observations framed by a named trading style and per-snapshot objective. Strictly observational — no broker write path. Runs entirely in Docker Compose.

Design + roadmap: `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`; per-feature specs alongside it, plans in `docs/superpowers/plans/`. **Load-bearing — read the relevant spec section before adding a feature.**

## Daily commands

Everything runs in Docker; Make targets wrap Compose. `make help` lists every target — below is only what `help` doesn't tell you.

| Command | What `help` omits |
|---|---|
| `make dev` | First run 3–8 min. Only `web`/`frontend` hot-reload. |
| `make e2e` | Brings up the `MOCK_EXTERNAL=true` stack, runs the lanes, tears down. Perf is separate (`make e2e-perf`). |
| `make e2e-one t=<lane/mod.py>` | Needs the overlay already up (`make e2e-up`). `HEADED=1` to debug. |

One backend test: `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (container WORKDIR is `/app/backend` — drop the `backend/` prefix).
One FE test: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`.
Fresh rebuild (catches reproducibility bugs): `docker compose down -v && docker compose build --no-cache && docker compose up -d`.

## Architecture big picture

**Six-service compose stack** (dev): `web` (Django+DRF+Channels/Daphne), `worker` (Celery), `beat` (`DatabaseScheduler`), `redis` (broker+Channels+cache), `db` (Postgres 17), `frontend` (Vite). All bind `127.0.0.1` only.

**Django project** `backend/config/`, settings `base.py`/`dev.py`/`prod.py`. Apps `backend/apps/<name>/`, imported `apps.<name>` (PYTHONPATH `/app/backend`). **Celery task packages are listed explicitly in `config/celery.py` (`TASK_PACKAGES`, not autodiscovered)** — add new task modules there. Every scheduled task is also inventoried in `apps/core/scheduled_tasks.py` (drift-gated) and asserted registered by `test_celery_registration.py`.

**App roster** (`backend/apps/`, 15 apps) — `core` (settings, health, drift-gated inventories), `market` (Schwab + free providers, TradingView MCP), `snapshots`, `ai` (providers, router, catalog, cost), `threads` (`Message`+`AIRun`, streaming consumer, compare, Coach, Files), `profiles`, `secrets` (encrypted creds + OAuth), `observer` (schedules, notifications, predictions, triggers, briefing), `backups`, `export`, `thesis` (theses, post-mortems, journal, positions, lessons), `analytics` (aggregations, dashboard rollup, evals), `recall` (pgvector search), `book` (daily risk reading), `strategy` (coverage, warroom, desk, regime).

**`/api/<x>/` paths do not track app names** — a 27→15 consolidation moved modules while leaving every route unchanged. Grep the URL, don't infer the app. Beat tasks *are* named for their owning app (`test_celery_registration` enforces the prefix). Non-obvious homes: `AIRun` lives in `threads`, not `ai`; `DecisionJournalEntry` in `thesis`, not `threads`.

**Adding a Django app:** use the `new-django-app` skill — it encodes the wiring, including the `config/urls.py` include placed **before** the generic `/api/`.

**Realtime channels (WS)** — groups joined in `connect()`, left in `disconnect()` (ref `apps/core/consumers.py`): `user.<id>.notifications`, `thread.<id>` (streaming tokens + `message_started`/`text_delta`/`message_done`/`cost`/`error` — `cost` follows `message_done` and carries `parent_message_id` for Compare branch routing), `snapshot.<id>` (per-section capture progress).

**`thread.<id>` reconnect replay buffer** — `event_log.py` stamps each event a monotonic `seq` and keeps the last 256; `ThreadConsumer.connect()` replays `seq > since` when `?since=` present. `WebSocketProvider.tsx` sends `?since=` only **on reconnect** (a tracked seq IS the reconnect signal). Seq-less channels never replay.

**Provider abstraction** — `apps/ai/providers/base.py` `Provider` protocol; `ClaudeProvider`/`OpenAIProvider`/`LocalProvider`, whose `run()` emits a normalized event union so the consumer is provider-agnostic. **Selection flows through `apps/ai/router.py` + `get_provider()` — do not instantiate providers directly from views/tasks.**

**Multi-provider fan-out** — `POST /api/threads/<id>/compare` runs one prompt across provider+model pairs in parallel, each its own branch. `…/stop/<message_id>/` sets a Redis flag that the streaming loop polls (~0.25s) before `gen.aclose()`ing the provider, halting generation+billing.

**Capture pipeline** — `apps/snapshots/services/` fills sections in one `snapshots.capture` task as a **synchronous loop** over `snap.includes` (spec §5 says a Celery chord; the loop is the real impl). A raising section is caught and marked `failed` (no retry, `error` scrubbed of key-bearing URLs); partial failures are OK and marked in the payload. Landmines:
- **The `vix` section is always-on** — `capture_for_existing` appends it to `includes` on every path (manual/observer/trigger/briefing) and it is never prunable. Free providers can't quote CFE futures, so without Schwab it degrades to spot-only **with an explicit note** — never silently omitted.
- **`chain` uses the first non-futures watchlist symbol** (Schwab chains 400 on futures; default SPY); its render appends an analytics block from `market/services/option_analytics.py`.
- **`breadth` drops A/D internals wholesale pre-open** until `advn+decn ≥ 100` — Schwab warm-up placeholders would otherwise read as real breadth. /ES and //NQ ride a **separate** quote call (Alpaca's fallback fails whole batches containing rejected futures symbols).
- **Longer-horizon OHLC stats are bounded by `ts <= captured_at`** — re-serializing an old snapshot (eval replays, re-pins) must never see post-capture bars.
- **Cash indices ($SPX, $TNX) report volume 0 on every bar** — the serializer omits the volume column with a note (zeros read as a broken feed to the AI).
- **Prune order under token pressure**: drop `watchlist_daily`, then truncate oversized OHLC to its newest bars, then `token_budget.py` drops whole sections (`chain→ohlc→news→fed→flowlite→breadth→quotes→positions`). Every other section, vix/macro/events included, is never prunable.
- **`macro` pairs FRED series with live CBOE yield-index quotes** (`market/services/yields.py`; indices quote yield×10). H.15 publishes ~1 business day behind — source-inherent, noted in the render.

**Event-trigger evaluator** — beat task `evaluate_triggers` every ~10s (NOT a long-running process). DSL is JSON: `all/any/not` + `{metric,ticker,op,value,window}` leaves. Spec §4.8, §7.2.

**Frontend routing** — all routes nest under `<AppLayout>`; only `/render/chart` bypasses it. Add routes as children in `frontend/src/router.tsx` with `handle: { crumb: "..." }`. Shortcuts are `g <x>` (`useKeyboardShortcuts.ts`). No `dangerouslySetInnerHTML` (FE XSS lint gates it).

## Non-obvious conventions

**Landmines** (silent failures) are the highest-value entries — preserve them when editing.

### Docker, tooling & tests
- **Editor errors about missing modules are expected** (everything runs in Docker); lint via `make lint`.
- **`beat` depends on `web` health** in `compose.yaml` — else `DatabaseScheduler` races `migrate` and crashes on an empty schema. Don't remove.
- **`ty` is advisory** (~900 false-positive Django diagnostics). Real gates: `ruff` + `pytest` + FE `eslint`/`tsc` + `vitest`.
- **All tool config is in `pyproject.toml`**; no `ruff.toml`/`pytest.ini`. **`uv.lock` is committed** (`uv sync --frozen`); regenerate with `uv lock` on host.
- **Only `web`/`frontend` hot-reload.** After adding/renaming a task module or `beat_schedule` entry, `docker compose restart worker beat` or it won't fire (fresh `up`/CI unaffected).
- **Worker image carries chromium** (Playwright); the render test passes only from `worker`. **Integration tests excluded by default** (`-m 'not integration'`).
- **`MOCK_EXTERNAL=true`** (set by `compose.e2e.yaml`) short-circuits Claude/OpenAI/Local/Schwab/Finnhub to fixtures. **Never set it on the dev stack** — provider unit tests patch the SDK client class directly (e.g. `patch("apps.ai.providers.claude.AsyncAnthropic", ...)`) and that patch sits *below* the `is_mock_mode()` short-circuit, so a stray `MOCK_EXTERNAL=true` makes them silently exercise canned fixture streams instead. If you see "Mocked response" in dev, recreate the containers.

### Backend wiring & security
- **URL include order** — `config/urls.py` registers specific prefixes (e.g. `/api/costs/`) **before** generic `/api/`. Don't reorder.
- **DRF exposes FK ids as `*_id`, not nested objects** — FE TS must use `thread_id` etc. verbatim (`thread` reads `undefined`).
- **Security is network isolation, not auth.** Binds `127.0.0.1`; DRF defaults `AllowAny`, no user token; WS is Origin-validated. **Do not bind `0.0.0.0` without adding real auth first.**
- **Encrypted secrets at rest** — Schwab/provider keys in `ProviderConfig`/`ApiCredential` (django-cryptography). Don't log them or expose without `write_only`. **All reads go through `apps/secrets/credentials.py::decrypt_token`** (degrades to skip on undecryptable token). Keep the `ApiCredential` import location — moving it breaks `<module>.ApiCredential` patch sites.

### Snapshots, images & rendering
- **Section terminal state is `"done"`; only the parent `Snapshot` uses `"ready"`.** Mixing them silently drops images (`_snapshot_image_ids()` filters `status="done"`).
- **Pinned snapshots reach the LLM as a synthetic first user turn** — `ThreadViewSet.create()` synthesizes a `done` user `Message` (`content["text"]=serialize_for_ai(snap)`, `snapshot_ref=snap`); observer/trigger paths do the same per fire. **Do not load the snapshot inside `_build_request()`** — the synthetic-message pattern keeps the pipeline provider-agnostic + UI-visible. Images attach separately via `_snapshot_image_ids()`.
- **Snapshot image bytes are offloaded to `/data`** (new rows: `file_path`, `data` NULL; legacy: in-DB). **Always read via `apps.snapshots.image_store.read_image_bytes(img)`, not `bytes(img.data)`.** Captures go through `image_store.create_image` (volume-write failure degrades to in-DB).
- **`TradingProfile.DEFAULT_INCLUDES` still seeds only an *empty* `default_includes`** (`TradingProfile.save()`) — changing the constant never reaches existing profiles without a data migration or a UI edit. Briefing captures hardcode `includes=['breadth']`.
- **Adding a snapshot section kind touches five surfaces**: `_FETCHERS` (`snapshots/services/__init__.py`), `SnapshotSection.KIND_CHOICES` (**≤16 chars**, `max_length=16`) + migration, `_title` + `_RENDERERS` in `serializer.py` (no renderer = the payload ships as a raw ` ```json ` dict dump), and the centralized FE list `frontend/src/lib/snapshotSections.ts` (`vix` is deliberately excluded — always-on, never user-selectable).
- **Rich default sections multiply scheduled-fire input tokens**, and live-quote lines make byte-identical prompts rare (cutting `OBSERVER_RESPONSE_CACHE_ENABLED` hits). Per-schedule `default_includes` is the lever.

### AI providers & capabilities
- **Tool use and structured output have provider parity; thinking/memory/files/citations are Claude-only.** One-shot structured output goes through `apps/ai/structured.py::run_structured(provider=…)`; callers resolve their target via `resolve_structured_target(profile=, override_provider=)` and cap-check with `ensure_within_caps`. **A profile/schedule model that is a catalog row of a *different* provider is ignored with a warning** and the provider's own default is used (`TradingProfile.default_model` defaults to a Claude id, so a profile switched to OpenAI would otherwise send that id to OpenAI). **Never import `providers/claude_structured.py` or `providers/openai_structured.py` outside `apps.ai`** (import-linter). Tools opt-in per profile (`enable_tools`); OpenAI/Local also gated on `ProviderConfig.supports_tools`. **Enabling a Claude-only feature elsewhere warns-and-continues** (`capabilities.unsupported_features(...)` → a `capability_warning` message + `warning` WS event).
- **Add a tool** by registering a `ToolSpec` in `apps/ai/tools/registry.py` (writes a `ToolCall` row, broadcasts `tool_call`/`tool_result`).
- **Files API** — deleting a `UserFile` also deletes it upstream; bytes don't live locally.
- **TradingView `tv_*` tools ride two different toolsets on purpose** — `registry.request_toolset()` (does ORM/Redis/HTTP) builds the *schemas* on the sync request path; the providers' async loops keep `default_toolset()`, whose pure `resolve_dynamic` dispatches by name. **Never call `request_toolset()`/`tradingview_toolset()` from provider code** (SynchronousOnlyOperation / blocked event loop). The read-only allowlist in `apps/ai/tools/tradingview.py` is the only source of exposable names.

### AI tokens, cost, caps & routing
- **Token counts are provider-aware** — `estimate_tokens(text, provider=, model=)` (Claude → Anthropic count_tokens; else tiktoken). New code should pass provider/model.
- **Per-model payload budgets live in the catalog** (`ModelInfo.max_payload_tokens`); `serialize_for_ai` resolves from `(provider, model)` — **don't hard-code 40k.** **The catalog is the only place an unknown model gets a budget or price** — a model id absent from `catalog.py` falls to a 40k budget and is billed at the provider's priciest row, so add new models there first.
- **Cost caps** — `cost.check_monthly_cap(...)` sums 30d of `AIRun.cost_usd`; null cap = no-op. Local cost is $0 (caps/meters hidden in UI).
- **Cross-provider failover** (opt-in `AI_FAILOVER_ENABLED`) — retry once on a secondary **only if the primary errored before emitting any token**; never after a token streamed (would duplicate).
- **Calibration-weighted routing** (opt-in `AI_CALIBRATION_ROUTING_ENABLED`) — the router query `.defer("_api_key")`s the encrypted column, else key rotation crashes routing.

### Observer, triggers & scheduling
- **Observer schedules drive beat via `OneToOneField(PeriodicTask)`** — the ViewSet calls `sync_periodic_task(...)` explicitly (no signals). Cron evaluates in `OBSERVER_BEAT_TIMEZONE` (default UTC).
- **Observer opt-in modes** (all default False): `structured`, `mode="diff"`, `use_batch` (Messages Batch — no streaming, the one Claude-only mode), `consensus` (needs structured), `investigate` (plain only).
- **Observer response cache** (opt-in `OBSERVER_RESPONSE_CACHE_ENABLED`) — a plain fire with a byte-identical prompt within TTL reuses the observation (`kind=cached_observation`).
- **NYSE market-hours** live in `apps.market.calendar` (`pandas-market-calendars`); `observer.services.market_hours` is a thin wrapper, not the implementation.
- **Market events are a forward calendar, not a session calendar** — `apps.market.MarketEvent` (earnings+macro from Finnhub) ≠ `apps.market.calendar` (sessions). Reads go through `events.upcoming_events(...)`. Macro degrades to `SEED_MACRO_EVENTS` — **and in practice the seed IS the macro source** (Finnhub's economic calendar is premium; free keys 403), so refresh `events_seed.py` before its dates lapse or every snapshot/briefing silently shows `macro: []`.
- **Only equity-like symbols reach Finnhub company endpoints + EDGAR** — gate with `symbols.is_equity_like` ("ES" is Eversource to Finnhub; indices/futures aren't SEC filers). Provider errors embed the key-bearing request URL — log via `safe_log.safe_err`, and anything user-facing goes through `safe_log.scrub_secret_params`.

### Thesis, post-mortems & calibration
- **Pre-trade discipline on thesis create** — `ThesisSerializer.validate` requires non-empty `rationale` AND an invalidation (`invalidation_price` OR `invalidation_note`), **create only** (edits/ORM/fixtures bypass).
- **Post-mortem objective verdict is deterministic — no AI key needed** — `postmortem.objective_verdict(thesis, fwd_pct)` (off `OHLCBar`, DEADZONE 1%). The Claude narrative layers on top and degrades silently to `report={}`; never raises out of `run_postmortem`.
- **Idempotent `scheduled→running` claim prevents double-billing** — `run_postmortem` opens with `filter(status="scheduled").update(status="running")`; 0 rows → exit. `THESIS_POSTMORTEM_HORIZONS=[7,30,90]`.
- **Eval calibration loop is look-ahead-safe** — replays a candidate against **frozen** source snapshots. **Feed the model ONLY `serialize_for_ai(snapshot)`, never the coach/recall** (a coach block leaks post-trade info). Scheduled beat opt-in/OFF (`AIEVAL_SCHEDULED_ENABLED`) — `run_structured` has no `MOCK_EXTERNAL` short-circuit, so an always-on schedule hits the real model.
- **`apps/market/returns.py` is the shared price-path helper** — analytics and post-mortems both import from there; don't inline.
- **`AgentPreset` builtins are seeded by a data migration** (`builtin` read-only; duplicate slug → 400). **pytest-django `serialized_rollback` does NOT restore data-migration-seeded rows under `--reuse-db`** — a `transaction=True` test wipes them, so `apps/profiles/tests/conftest.py` re-seeds via an autouse fixture; mirror that for any migration-seeded table.

### Analytics, Coach & scorecards
- **Analytics are on-demand, never scheduled** — DRF views under `/api/analytics/` aggregating off indexed columns at request time. No Celery tasks/materialized views.
- **Observer timeline reads Messages, not a run log** — no `ObserverRun` table; one Message per fire (assistant/done=success, assistant/failed=failure, system/done=cost-cap skip).
- **The Coach** (`coach.py`) injects calibration + cohort base-rate + distilled-lessons blocks. **All read decisive completed post-mortems only (look-ahead-safe)** and degrade via `_safe()`.

### Data sources, predictions & coverage
- **Free data sources + graceful fallback** — `services/fallback.py` routes quotes/OHLC/chain/news to a free provider when Schwab isn't connected. Keys are `ApiCredential` rows backed per-field by `DATA_SOURCE_ENV_KEYS` env vars (DB wins); all reads via `decrypt_token`. **UI-saved keys die with the Docker volumes** — `down -v` removes the credential rows AND the `/data` Fernet salt, and either loss alone destroys them. Env-backed keys survive rebuilds; tests get `DATA_SOURCE_ENV_KEYS={}` via a `backend/conftest.py` autouse fixture so a developer's real keys can't flip "not configured" assertions.
- **Prediction Ledger** — `apps.observer.AIPrediction` is **auto-extracted** from a structured `ObservationReport` (`None` never breaks the fire). Dedup: ≤1 `open` per `(ticker, horizon, profile)` — a same-direction re-fire is a no-op (the call stays frozen for honest calibration); a flip invalidates+reopens.
- **COVERAGE — living per-ticker house view** — `apps.strategy.CoverageNote` revised **with a reason** behind a **hysteresis gate** (writes a `CoverageRevision` only on created OR material_change OR stance/conviction delta; else reaffirm, no churn). Best-effort, `None` on no-key/cap/error. Observer auto-revises **by existence** (queues only if the primary ticker already has a note). **Gotcha:** a broad `coverage/` line in `.gitignore` swallowed `backend/apps/strategy/coverage/`; a `!`-negation keeps it tracked — any new dir colliding with a common ignore pattern hits this.
- **TradingView (official MCP server) is the FIRST fallback** for quotes/bars/news when Schwab is disconnected, and the macro-calendar source ahead of `SEED_MACRO_EVENTS`. "Configured" = `tradingview.is_connected()` = token present AND no `provider_health` auth-error marker — that marker (1h TTL) is the circuit breaker after a rejected token; a separate 60s marker (`mark_rate_limited`) breaks on HTTP 429. Symbols are `EXCHANGE:TICKER` (`$VIX`/`/ES` map through `INDEX_SYMBOLS`/`FUTURE_SYMBOLS`; equities resolve via `search_symbols`, a miss caching as `""`). Breadth internals have no TradingView equivalent → empty, never an error. Token refresh is **lazy** in `ensure_fresh_token()` under a Redis lock — no beat task, don't add one. Result shapes are normalized leniently — confirm against the live `tools/list` fixture (spec §9) before trusting a new field.

### Frontend & runtime config
- **Frontend primitives** — reach for `Skeleton`/`EmptyState`/`ErrorBoundary`/`Toasts` before ad-hoc spinners/text/try-catch. Toasts need a `<ToastProvider>` (AppLayout provides one).
- **Notifications are user-anonymous** — `Notification.user` nullable; consumer on `user.anonymous.notifications`. **`Notification.kind` is `varchar(16)`** — a longer kind string silently overflows at write time (`cal_drift`, not `calibration_drift`).
- **UI-configurable runtime settings** — `runtime_config()` resolves `SystemSettings.<field> ?? settings.<DEFAULT>` (singleton, no restart). **Sync-context knobs only** — the async-ORM boundary keeps per-stream knobs env-only.
- **Local provider needs `host.docker.internal`** (mapped in `compose.yaml`) **+ lists its own models** — the provider probe calls `list_models()` and persists `discovered_models`. **Do not add SSRF private-IP filtering to the probe** — local endpoints are on localhost/private addresses by design.
- **Dashboard rollup is fault-isolated per section** — `GET /api/dashboard/` returns five sections each wrapped by `_safe(fn, default)`. **Defaults MUST be full contract-valid shapes** (e.g. `{"armed_count":0,"latest_firings":[]}`, not `{}`) — a `{}` default crashes the SPA tile that reads `latest_firings.length`.
- **Morning Briefing** — `assemble.py` gathers deterministic sections (each wrapped so it never raises); `run.py` posts a synthetic user `Message` into a `kind="briefing"` thread. The beat task runs every 15 min but fires once/day via a unique `scheduled_date` claim.

## Testing

- **Integration** tests use real Postgres, `fakeredis`, Celery eager. **External APIs are mocked at the SDK client class** via `unittest.mock.patch` (e.g. `AsyncAnthropic`), not `respx`/`vcrpy`.
- **E2E**: six lanes under `e2e/` on the full stack (`MOCK_EXTERNAL=true`). Design: `docs/superpowers/specs/2026-04-18-e2e-comprehensive-design.md`.
- **Frontend**: `vitest` + `@testing-library/react`; don't duplicate E2E. Backend unit tests favor `parametrize`.

### Quality gates (CI) — landmines

`make lint`/`make check` run them (config in `.github/workflows/`, `pyproject.toml`). mypy is a real gate (zero baseline); `ty` advisory. Supply-chain `pip-audit`/`pnpm audit` are **BLOCKING**.

- **Architecture contracts** (`import-linter` + FE `dependency-cruiser`) — concrete AI providers private to `apps.ai`; crypto (`apps.secrets.{fields,keys}`) private to `apps.secrets`; FE `src/api` must not import `src/{pages,components}`. A direct import elsewhere reds CI. (`depcruise` needs a glob, not a bare dir.)
- **OpenAPI contract** — `backend/schema.yml` + `frontend/src/api/schema.d.ts` are committed + drift-gated (source of the `*_id` contract); regenerate with `make schema` + `pnpm gen:api`.
- **Coverage floors** — backend `fail_under=86` (branch coverage on), FE vitest + a `type-coverage` `any`-ratchet. Property tests (Hypothesis) cover DSL/token-budget/cost/market-hours; `gitleaks` scans staged + CI history.
- **Semgrep landmine rules** (`tools/semgrep/rules/`) — several landmines above are executable rules (`bytes(img.data)`, `0.0.0.0` bind, `_safe(_, {})`, secret logging).
- **`deptry`** (gate) — **run after `uv sync`** (needs installed metadata to map `rest_framework`→`djangorestframework`); `uvx deptry` is noisy.
- **`ruff C901`** complexity ≤15 and **`ruff S`** (bandit) are gates — no hardcoded secrets/weak hashes/shipped `assert` (real guards must survive `python -O`; `S101/5/6` ignored in tests/e2e).
- **N+1 guards** — `django_assert_max_num_queries` pins budgets. Add one per new bounded aggregation.
- **Prompt-injection boundary** (code, not CI) — `coach.build_system_prompt` ALWAYS prepends a "data boundary" directive marking the user turn (snapshot/news/filings/tool output) as untrusted DATA, on every live run path (NOT the look-ahead-safe eval). **Don't drop it when refactoring.**
- **Determinism + flakes** — `pytest-randomly` runs locally/nightly, but the **per-commit gate runs `-p no:randomly`**. `backend/conftest.py` autouse fixtures reset calendar cache + channel layers + set Hypothesis `deadline=None` — keep them. Streaming providers dispatch ORM-touching tools off the loop via `sync_to_async(thread_sensitive=True)`; **do NOT set `DJANGO_ALLOW_ASYNC_UNSAFE`** (corrupts the connection, cascades `OperationalError`).
- **Inventory drift gates** — `feature_flags.py` (every `env.bool` flag) + `scheduled_tasks.py` (every `beat_schedule` task) are CI-gated against live code; add the registry entry in the *same* change or CI reds.

## Workflow

Planning uses the superpowers skills (`brainstorming` → `writing-plans` → `subagent-driven-development`); specs land in `docs/superpowers/specs/`, plans in `docs/superpowers/plans/` (`YYYY-MM-DD-<topic>.md`). Commits bite-sized + conventional; `make check` must pass before commit.
