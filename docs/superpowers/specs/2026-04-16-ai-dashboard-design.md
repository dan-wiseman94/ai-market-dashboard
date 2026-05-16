# AI Trading Dashboard — Design

**Date:** 2026-04-16
**Status:** Approved for planning
**Owner:** Daniel Wiseman

## 1. Goal

A single-user desktop application, run via Docker Compose, that captures rich snapshots of the stock market and routes them to a chosen AI (Claude, OpenAI, or a local OpenAI-compatible endpoint) for observations and suggestions, framed by a named trading style and a per-snapshot objective. The app supports three interaction modes on the same capture pipeline:

1. **One-shot consult** — snapshot + ask once.
2. **Ongoing chat** — pin a snapshot to a conversation; follow up with questions.
3. **Scheduled observer** — cadence-driven captures per profile + event-triggered captures on conditions (price moves, volume spikes, P&L thresholds, VIX levels).

Strictly observational: no order placement, no write path to the broker.

## 2. Stack

- **Backend:** Django 5 + Django REST Framework + Django Channels (ASGI via Daphne).
- **Workers:** Celery worker + Celery beat. The event-trigger evaluator runs as a beat-scheduled task (§7.2), not a separate container.
- **Broker / cache / channels layer:** Redis 7.
- **Database:** PostgreSQL 16.
- **Frontend:** Vite + React 18 + TypeScript, TailwindCSS + shadcn/ui, TanStack Query v5, Zustand, React Router v6, `lightweight-charts`.
- **Chart rendering (server-side):** Playwright headless, navigating the frontend's own chart route for fidelity.
- **Data sources:** Charles Schwab (quotes, chains, OHLC, positions, breadth) + one news API (Finnhub / Marketaux / Polygon — selected at config time).
- **AI providers:** pluggable — Anthropic SDK (Claude), OpenAI SDK (OpenAI cloud + any OpenAI-compatible local endpoint: Ollama, LM Studio, vLLM, llama.cpp, LocalAI).
- **Deploy:** Docker Compose, binds to `127.0.0.1` by default.

## 3. System architecture

### 3.1 Compose services

| Service | Base | Purpose |
|---|---|---|
| `web` | python:3.12-slim + Daphne | HTTP API (DRF) + WebSockets (Channels) |
| `worker` | python:3.12 + Playwright image | AI runs, market fetches, chart rendering, event evaluator |
| `beat` | python:3.12-slim | Celery beat (dynamic schedules via `django-celery-beat`) |
| `redis` | redis:7-alpine | Broker, Channels layer, response cache |
| `db` | postgres:16-alpine | Persistence |
| `frontend` (dev only) | node:20-alpine | Vite dev server with HMR |

Prod: frontend is pre-built (`npm run build`) and served by Django through Whitenoise; `frontend` container is dropped.

### 3.2 Django apps

One concern each, small surface:

- `core` — settings, base models, single-user token shim, health endpoints.
- `market` — Schwab + news clients, quote/chain/OHLC/breadth services, Redis cache layer.
- `snapshots` — snapshot domain, capture orchestration, AI-payload serialization.
- `profiles` — trading styles; Watchlists live here too.
- `ai` — provider abstraction, streaming, cost tracking, catalog.
- `threads` — conversation persistence (consult / chat / observer timeline).
- `observer` — scheduled runs, event-trigger definitions, evaluator.
- `notifications` — dispatch to WebSocket (v1); webhook sinks later.
- `charts` — client-upload endpoint + Playwright server renderer.

### 3.3 WebSocket channels

- `user.<id>.notifications` — trigger fires, observer completions, errors, cost-cap events.
- `thread.<id>` — streaming AI tokens, message lifecycle.
- `snapshot.<id>` — capture progress (per-section `started | done | failed`).

Single WS connection per browser tab, authenticated by the user token; subscriptions are lazy per-component.

## 4. Data model

### 4.1 Identity & config

- **User** — single row. Preferences.
- **ProviderConfig** — one row per provider (`claude`, `openai`, `local`). Encrypted API key, base URL, default model, `supports_vision`, `enabled`, `daily_cost_cap_usd`.
- **ApiCredential** — Schwab OAuth tokens (access + refresh + expiry), news API key. Encrypted.

### 4.2 Trading config

- **TradingProfile** — name, style text, default_includes (JSON list of section kinds), default_provider, default_model, active.
- **Watchlist** — name.
- **WatchlistSymbol** — ticker, sort_order, watchlist FK.

### 4.3 Market data (cached / historical)

- **Quote** — ticker, bid, ask, last, volume, ts.
- **OHLCBar** — ticker, timeframe (`1m|5m|15m|1h|1d`), o/h/l/c/v, ts. Indexed `(ticker, timeframe, ts DESC)`.
- **OptionChain** — underlying, expiry, fetched_at, raw JSON; children **OptionContract** (strike, type, bid, ask, iv, delta, gamma, theta, vega, oi, volume).
- **NewsArticle** — ticker (nullable), headline, source, url, published_at, summary.
- **Position** — ticker, qty, avg_cost, mkt_value, unrealized_pl, day_pl, as_of.
- **MarketContext** — spy, qqq, vix, breadth fields, as_of.

### 4.4 Snapshot domain

- **Snapshot** — id, profile FK, objective (text), status (`pending|ready|failed`), captured_at, includes (JSON), notes (user text for this capture), source (`manual|observer|trigger`), summary_hash.
- **SnapshotSection** — snapshot FK, kind (`quotes|chain|ohlc|positions|breadth|news|notes|image`), payload_json, source_refs (JSON list of FK ids into market rows), status, error.
- **ChartImage** — snapshot FK, ticker, timeframe, origin (`client|server`), file (`/data/charts/<snapshot_id>/<uuid>.png`).

### 4.5 Conversations

- **Thread** — kind (`consult|chat|observer`), title, created_at, profile FK (nullable), pinned_snapshot FK (for consult/chat), schedule FK (for observer).
- **Message** — thread FK, role (`user|assistant|system`), content (JSON block list), snapshot_ref FK (nullable), parent_message FK (nullable — set on assistant messages produced by multi-provider compare, §6.6), created_at.
- **AIRun** — message FK, provider, model, input_tokens, output_tokens, cached_tokens, cost_usd, latency_ms, status, error, raw_request_summary.

### 4.6 Observer + triggers

- **ObserverSchedule** — profile FK, enabled, cadence_cron, market_hours_only, last_fired_at.
- **EventTrigger** — name, profile FK (nullable), condition (JSON DSL, see §4.8), cooldown_seconds (default 1800), enabled, last_fired_at.
- **TriggerFiring** — trigger FK, fired_at, payload (matched values), snapshot FK, thread FK (nullable).

### 4.7 Notifications

- **Notification** — user FK, kind (`trigger|observer_done|error|cost_limit`), title, body, read_at, link, meta JSON.

### 4.8 Event-trigger condition DSL

JSON, stored on `EventTrigger.condition`:

```json
{"all": [
  {"metric": "price",      "ticker": "SPY",  "op": ">",  "value": 550},
  {"metric": "pct_change", "ticker": "NVDA", "op": ">=", "value": 0.02, "window": "5m"}
]}
```

- Top-level ops: `all`, `any`, `not`.
- Leaf ops: `>`, `>=`, `<`, `<=`, `==`, `crosses_above`, `crosses_below`.
- `window`: required for delta metrics. Values: `1m|5m|15m|1h|1d`.
- Metrics (v1): `price`, `pct_change(window)`, `volume_z(window)`, `position_pl`, `position_pl_pct`, `vix`.
- `crosses_above` / `crosses_below` use the two most-recent evaluator ticks to detect a sign change.

### 4.9 Indexes

`Snapshot(captured_at DESC)`, `Thread(created_at DESC)`, `Message(thread_id, created_at)`, `OHLCBar(ticker, timeframe, ts DESC)`, `Quote(ticker, ts DESC)`, `TriggerFiring(fired_at DESC)`, `Notification(user_id, read_at, created_at DESC)`.

### 4.10 Retention

Nothing auto-pruned in v1. Charts live on disk at `/data/charts/`. A daily pg_dump runs to `/data/backups/YYYY-MM-DD.sql.gz`, keeping the last 7 days.

## 5. Snapshot pipeline

All three AI modes ultimately call `snapshots.services.capture(...)`.

### 5.1 Orchestration

```
capture(profile, objective, includes, notes, source):
  1. Create Snapshot(status="pending").
  2. Fan out parallel Celery subtasks per section in `includes`:
     - fetch_quotes(watchlist_tickers)
     - fetch_ohlc(tickers, timeframe, bars)
     - fetch_chain(underlying, expiries)
     - fetch_positions()
     - fetch_breadth()
     - fetch_news(tickers, lookback_hours)
     - render_charts(ohlc_sections)  # server-side via Playwright
  3. Group callback: finalize_snapshot(snapshot_id)
     - status="ready" if any section succeeded; "failed" if all failed
     - broadcast `snapshot.<id>.ready` on Channels
     - if source != "manual": auto-start an AI run on the profile's default provider
```

Each subtask is idempotent with its own retry policy (exponential backoff on 429; Anthropic `overloaded_error` optionally falls back to a smaller Claude model if `ProviderConfig.fallback_model` is set).

### 5.2 Redis cache TTLs

- Quotes: 5s
- OHLC 1m: 30s · 5m: 2min · 15m: 5min · 1h: 15min · 1d: 1h
- Option chains: 15s
- Breadth: 30s
- News: 5min
- Positions: 10s

Cache key: `market:<kind>:<ticker>:<params_hash>`. `SnapshotSection.source_refs` records which cached payload produced each section.

### 5.3 AI payload serialization

`snapshots.serialize_for_ai(snapshot) -> AIPayload` formats sections into compact, token-efficient prompts:

- **Quotes** → markdown table, up to 8 columns (ticker, last, %chg, bid, ask, volume, high, low).
- **OHLC** → CSV in fenced code block, last N bars only.
- **Option chain** → filtered to ±10 strikes around ATM by default; condensed table with greeks.
- **News** → headline + one-line summary + source; cap 15 items, newest first.
- **Positions** → markdown table with totals row.
- **Notes + objective** → placed at the top of the user message.
- **Profile style text** → **system prompt**, marked with Anthropic `cache_control: ephemeral` for prompt-cache hits when chatting in the same thread.
- **Chart images** → multimodal image blocks (Claude native, OpenAI `image_url` or base64).

### 5.4 Token budget guard

Before sending, estimate tokens with `tiktoken` (OpenAI) or `anthropic.count_tokens` (Claude). If estimate > `model_context * 0.6`, progressively prune: chain first, then older news, then older OHLC bars. UI shows which sections were pruned.

### 5.5 Partial-failure handling

Capture succeeds with partial data. The serializer explicitly marks missing sections in the payload, e.g.:

```
## News
_(unavailable: Finnhub returned 503)_
```

UI renders per-section progress (`✓ quotes`, `✓ chain`, `✗ news — Finnhub 503`, `⋯ positions`) live over the `snapshot.<id>` channel.

### 5.6 Cost circuit breaker

Daily cost cap per provider (`ProviderConfig.daily_cost_cap_usd`). When exceeded:

- **Manual / chat** runs are blocked with a UI banner.
- **Observer** runs silently skip (logged).
- **Trigger** firings still create a `Notification(kind="cost_limit")` so the user knows the trigger fired even though no AI call was made.

## 6. AI provider abstraction

### 6.1 Interface

```python
class Provider(Protocol):
    name: str  # "claude" | "openai" | "local"
    async def list_models(self) -> list[ModelInfo]
    async def run(self, req: RunRequest) -> AsyncIterator[RunEvent]
    def estimate_cost(self, req: RunRequest) -> CostEstimate
```

- `RunRequest`: messages, model, system, max_tokens, temperature, images, cache_hint.
- `RunEvent`: normalized union — `text_delta | image_ref | usage | done | error`.

### 6.2 Implementations

- **ClaudeProvider** — `anthropic` SDK. Streaming via `messages.stream`. Prompt caching via `cache_control` on the system block. Native vision.
- **OpenAIProvider** — `openai` SDK against api.openai.com. Streaming via Responses or chat.completions.
- **LocalProvider** — same `openai` SDK with user-configured `base_url` + optional key. Vision is opt-in per-model via `ProviderConfig.supports_vision`.

### 6.3 Model catalog

`ai/catalog.py` ships a curated list per provider with input/output/cached pricing per 1M tokens. `list_models()` merges catalog entries with API discovery (Anthropic + OpenAI both offer list endpoints). Models not in the catalog are flagged `cost_unknown=True`:

- **LocalProvider** runs them normally at zero cost (local is free).
- **Hosted providers (Claude, OpenAI)** fall back to the highest-priced catalog entry for that provider as a safety ceiling for cost-cap math. The UI shows "Cost estimate uses ceiling pricing — add this model to the catalog for exact math." Updating the catalog is a PR, not a runtime step.

### 6.4 Streaming path

```
POST /api/threads/<id>/send {content, images?, provider?, model?}
  → 202 {message_id}
  → Celery task ai.run_thread(thread_id, message_id)
  → provider.run() yields events
  → each event broadcasts on `thread.<id>` Channels group
  → React consumer appends deltas to the live Message
  → on `done`: persist AIRun (usage, cost, latency) + finalize Message
  → on `error`: emit error event; Message stored with status="failed"
```

No SSE; the pre-existing WebSocket handles all streaming.

### 6.5 Routing precedence

Most-specific wins:

1. `Message.override_provider` (explicit per-send override)
2. `Thread.default_provider`
3. `TradingProfile.default_provider`
4. `ProviderConfig` first enabled (global fallback)

### 6.6 Multi-provider compare

`POST /api/threads/<id>/compare {content, providers: ["claude/opus-4.7", "openai/gpt-5"]}` creates **one user Message** (the prompt) and **N assistant Messages**, one per provider, all children of the same user message (`parent_message_id` FK on Message). Each assistant message has its own streaming `thread.<id>.branch.<branch_id>` sub-channel. Each gets its own `AIRun`. The UI renders side-by-side columns; replies to the thread after compare pick one branch to continue from (or branch again).

### 6.7 Image handling

Snapshot images served at `/api/images/<id>` (token-auth). Always sent inline (base64) — keeps LocalProvider working without network routing tricks and avoids any public-URL dependency for OpenAI.

## 7. Observer + event triggers

### 7.1 Scheduled observer

Celery beat reads `ObserverSchedule` rows via `django-celery-beat`, so UI edits take effect without restart.

```
run_observer(schedule_id):
  sched = ObserverSchedule.objects.get(id=schedule_id)
  if sched.market_hours_only and not is_market_open(now_utc): return
  if not sched.enabled: return
  snapshot = capture(profile=sched.profile, objective=None, source="observer", ...)
  thread = get_or_create_observer_thread(sched.profile)
  ai.run_thread(thread.id, user_msg=serialize_for_ai(snapshot))
```

One observer thread per profile, append-only. UI renders as a timeline with each turn collapsible.

Market-hours check: `pandas-market-calendars` against NYSE calendar (holiday + half-day aware).

### 7.2 Event-trigger evaluator

A Celery beat-scheduled task `evaluate_triggers` runs every `TRIGGER_TICK_SECONDS` (default 10s) on the main worker queue. Each tick is short (batched quote fetch + in-memory condition eval), so this does not need a dedicated worker. Redis-backed task-level locking (`single-instance: true`) prevents overlapping ticks if one runs long.

```
evaluate_triggers():  # fires every TRIGGER_TICK_SECONDS via beat
  triggers = EventTrigger.objects.filter(enabled=True)
  metrics = prefetch_metrics_for(triggers)  # batch Schwab quotes + positions once per tick
  for t in triggers:
    if in_cooldown(t): continue
    if evaluate(t.condition, metrics):
      fire(t, matched_values)

fire(trigger, values):
  with redis_lock(f"trigger:{trigger.id}"):
    TriggerFiring.objects.create(trigger=trigger, fired_at=now(), payload=values)
    trigger.last_fired_at = now(); trigger.save()
    snapshot = capture(profile=trigger.profile, source="trigger",
                      notes=f"Triggered: {trigger.name}")
    thread = Thread.objects.create(kind="chat", pinned_snapshot=snapshot,
                                   title=f"{trigger.name} fired at {now():%H:%M}")
    ai.run_thread(thread.id, user_msg=serialize_for_ai(snapshot))
    Notification.objects.create(user, kind="trigger", title=trigger.name,
                                body=describe(values), link=f"/threads/{thread.id}")
    broadcast `user.<id>.notifications`  # UI toast + OS notification
```

### 7.3 Condition evaluator

Pure Python, recursive, deterministic (`observer.conditions.evaluate(node, metrics) -> bool`). Metrics prefetched per tick; crossing ops compare the last two ticks stored in Redis with a short TTL.

### 7.4 Dedup / idempotency

- Redis lock per-trigger prevents concurrent dupes.
- `cooldown_seconds` blocks re-fires within the window.
- `django-celery-beat` handles observer schedule single-run semantics.

### 7.5 Notifications

Single `Notification` row per event; `NotificationSink` interface has one implementation in v1 (`WebSocketSink`). Webhook sinks are future work and already have their seat at the interface.

## 8. Frontend

### 8.1 Routes

```
/                       Dashboard (live quotes + open threads + recent triggers)
/snapshot               Compose snapshot (profile, sections, objective)
/threads                Thread list (filters: kind, profile, date, ticker)
/threads/:id            Thread view (streaming chat)
/threads/observer/:p    Observer timeline per profile
/market/:ticker         Per-ticker view (chart + chain + news)
/profiles               Manage trading profiles
/watchlists             Manage watchlists
/triggers               Visual rule builder
/schedules              Manage observer schedules
/settings               Provider configs, Schwab/news keys, cost caps
/costs                  Usage dashboard
```

### 8.2 Realtime layer

One `WebSocketProvider` at the app root. `useChannel(channelName, handler)` hook subscribes lazily; on reconnect, components resubscribe. Handlers can both update local state and nudge TanStack Query via `setQueryData` / `invalidateQueries`.

### 8.3 Streaming chat

`StreamingMessage.tsx` renders partial markdown (`react-markdown` + `remark-gfm`) as `text_delta` events arrive. Stop button issues `DELETE /api/runs/<id>` which revokes the Celery task and closes the provider stream.

### 8.4 Chart component

Single `Chart.tsx` built on `lightweight-charts`. Three roles:

1. Rendered in the live UI.
2. Captured client-side via `html2canvas` for "snap what I'm looking at".
3. Navigated to by Playwright at `/render/chart?ticker=…&timeframe=…&bars=…` for server-side capture. Deterministic: URL params fully specify the render; no user state bleeds in.

### 8.5 Snapshot composer

Single screen (not a wizard):

- Left: profile selector + style preview + default includes.
- Center: section checkboxes with inline config (tickers, expiries, bar count).
- Right: objective textarea + estimated tokens + per-provider cost estimate.
- Bottom: Capture button → navigates to the new thread mid-stream.

### 8.6 Trigger builder

Visual condition builder: rows of `[metric][ticker][op][value][window?]` joined by AND/OR (no nested groups in v1). Serializes to the JSON DSL.

### 8.7 Notifications UI

Bell icon with unread count. Dropdown lists `Notification` rows. On first trigger firing, prompts for `Notification.requestPermission()`; accepted permission drives OS-level notifications for `kind="trigger"` whenever the tab is loaded in the browser (works even when the tab is backgrounded or the browser is minimized, which is the whole point).

### 8.8 Authentication

Single-user, localhost. On first boot the backend generates a random token and writes it to `/data/user.token` (file mode 600). On the first HTTP request from `127.0.0.1`, `/api/bootstrap` reads the token file and sets an `HttpOnly; SameSite=Strict` session cookie bound to that token. All subsequent API calls and the WebSocket upgrade check the cookie. The token is also rotatable via `make rotate-token` (rewrites the file, invalidates existing sessions). No password UI.

### 8.9 State boundaries

- Server state → TanStack Query.
- Ephemeral UI state → Zustand.
- Realtime → WebSocket context → TanStack cache updates.

### 8.10 Theme

Dark by default, Tailwind `dark:` variants, toggle in settings.

## 9. Secrets

- Dev: `.env` (gitignored) via `django-environ`. `.env.example` committed.
- Runtime: all third-party keys live in `ProviderConfig` / `ApiCredential` rows, encrypted with `django-cryptography`. Encryption key derived from `DJANGO_SECRET_KEY` + a per-install salt at `/data/secret.salt` (generated if absent).
- Schwab OAuth tokens stored encrypted; refresh 5min before expiry via scheduled Celery task.
- No secret is ever logged. Provider client wrappers redact `Authorization` headers in debug traces.

## 10. Schwab auth flow

1. User clicks "Connect Schwab" in `/settings`.
2. Frontend opens Schwab's auth URL in a new tab (app `client_id` + `redirect_uri=http://127.0.0.1:8000/api/schwab/callback`).
3. Consent → Schwab redirects to the callback with `code`.
4. Backend exchanges code → tokens; stores encrypted in `ApiCredential`; redirects to `/settings?schwab=connected`.
5. Refresh tokens last 7 days; notification fires 24h before expiry.

## 11. Error handling

- **Backend exceptions** → DRF exception handler returns `{code, message, details}`. Celery failures create a `TaskError` row + an `error` event on the relevant WS channel.
- **Provider errors** classified: `transient` (retry backoff), `invalid_input` (user-facing, no retry), `rate_limit` (jittered retry), `auth` (surface in settings with re-authorize CTA), `cost_cap` (circuit breaker).
- **Frontend** — `ErrorBoundary` per route + per-mutation `onError`; toasts and `/api/client-errors` logging.
- **Partial snapshots** usable — missing sections explicitly marked in the AI payload.

## 12. Testing strategy

1. **Unit** (`pytest` + `pytest-django`): condition evaluator, payload serializer, cost calculator, market-hours, DSL parser, token estimator.
2. **Integration** (pytest-django + real Postgres via `testcontainers`, Redis via `fakeredis`, Celery eager): Django models, DRF endpoints, Celery task flow. Schwab / news / AI mocked at SDK boundary with `respx` / `vcrpy`.
3. **End-to-end** (`playwright-python` + `docker compose -f compose.test.yml`): one happy-path scenario per top-level route, all external services mocked at HTTP layer.

Frontend: `vitest` + `@testing-library/react` for components/hooks. No duplicate E2E in Vitest.

CI: `make check` → `ruff + mypy + pytest + vitest`. Docker image build is the final gate.

## 13. Observability

- `structlog` JSON in prod, pretty in dev. Context vars: `request_id`, `run_id`, `snapshot_id` propagated via Celery headers.
- `/api/health` (liveness), `/api/ready` (Postgres + Redis + Schwab token freshness).
- No Prometheus / tracing in v1; exporter drops in cleanly on `web` + `worker` later.

## 14. Dev workflow

```
make dev          # docker compose up --watch (hot reload)
make shell        # exec bash in web
make migrate
make test
make lint
make logs s=worker
make restore file=...
```

Volumes: `pg_data`, `redis_data`, `app_data` (`/data`). `compose.yaml` is dev; `compose.prod.yaml` overrides frontend and serves static from `web`.

## 15. Out of scope for v1 (YAGNI)

- Multi-user / teams / RBAC.
- Webhook notification sinks (interface exists, not implemented).
- Order placement / any write path to Schwab.
- Push-streaming from Schwab (v1 polls; streaming is a later optimization).
- Paper-trading simulator.
- Backtesting.
- Mobile-specific views (desktop-first; responsive layout is nice-to-have).
- i18n.
- Metrics / tracing / Sentry integration.

## 16. Milestones (rough, for planning)

1. **M1 — Skeleton**: Compose stack boots; Django + Channels + Celery + Redis + Postgres + React app all talk; `/api/health` green.
2. **M2 — Market data core**: Schwab OAuth + quotes + OHLC + positions + breadth; Redis cache; basic watchlist UI.
3. **M3 — Snapshots + AI**: Capture pipeline; serializer; Claude provider with token streaming over WebSocket; one-shot consult mode.
4. **M4 — Full threads**: Ongoing-chat thread mode (multi-turn, prompt-cache); OpenAI + LocalProvider; cost tracking + caps.
5. **M5 — Option chains + news + images**: OptionChain model + chain view; news ingestion; client screenshot + Playwright server render.
6. **M6 — Observer**: Schedules, beat integration, observer timeline UI.
7. **M7 — Event triggers**: Evaluator worker, DSL, visual builder, notifications + OS notifications.
8. **M8 — Polish**: Multi-provider compare, costs dashboard, backups, export, E2E tests.
9. **M9 — AI platform v2**: Provider-aware token counting + raised per-model payload budgets; cache-breakpoint on the last prior turn for multi-turn Claude runs; monthly cost cap parity with daily cap; structured Observer outputs (Pydantic `ObservationReport` + `messages.parse`); snapshot diff service + `/api/snapshots/<id>/diff/` endpoint; Observer diff-mode and Messages-Batch-mode schedules (50% cheaper sweeps); `/api/triggers/backtest/` DSL replay over stored OHLC; frontend primitives (`Toasts`, `Skeleton*`, `EmptyState`, `ErrorBoundary`); Cmd/Ctrl-K command palette. Plan: `docs/superpowers/plans/2026-04-18-m9-ai-platform-v2.md`.
10. **M10 — AI platform v2.5**: Tool use on Claude with five-tool default registry (`get_quote`, `fetch_ohlc`, `search_news`, `get_option_chain`, `compute_indicator`) + `ToolCall` audit rows + WS `tool_call`/`tool_result` events; per-profile Memory namespace (`memory_20250818` tool routed via beta channel); extended-thinking flag (per profile) + `thinking_delta` WS events; Anthropic Files API proxy (`apps.files.UserFile`) with upload/list/delete + `/api/threads/<id>/attach-file/`; `ChatMessage.content` widened to `str | list[dict]`; citation serialization helper (`apps.ai.citations.news_to_search_result_blocks`); frontend `ToolCallTrace`, `Citation`, `FileAttachPanel` + `useFiles` hook wired into `ThreadDetailPage`. Plan: `docs/superpowers/plans/2026-04-18-m10-ai-platform-v25.md`.
11. **M11 — Second brain**: Thesis objects, decision-journal close-of-thread prompt, post-mortem scheduler (7/30/90-day AI replay), agent presets (earnings prep, devil's advocate, pre-trade bias check, triage pass).
12. **M12 — Analytics**: Five on-demand analytics surfaces backed by `apps.analytics` — provider leaderboard, cost-per-insight, trigger heatmap, observer timeline, unusual-options interpreter. All under `/api/analytics/`; rendered on a new `/analytics` page with five cards. Plan: `docs/superpowers/plans/2026-04-18-m12-analytics.md`.

Each milestone is independently shippable and usable.

**Future (not yet in flight):**
- **M10.5 — Provider parity**: Bring tool-use / thinking / citations / files to OpenAI (GPT-5 responses API) and Local. Today these are silent no-ops for non-Claude providers.
