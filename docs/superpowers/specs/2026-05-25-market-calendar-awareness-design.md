# Market-Calendar Awareness (Multi-Calendar, App-Wide) — Design

**Date:** 2026-05-25
**Status:** Approved (design); implementation pending
**Related:** `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` §3.3 (channels), §4 (observer), §7 (triggers); `2026-04-18-m7-event-triggers-design.md`; `2026-04-17-m6-observer-design.md`

## 1. Goal & Non-Goals

**Goal.** Introduce one shared market-calendar service that:

1. Supports market calendars **beyond NYSE** — US bonds (SIFMA), CME/CFE futures, 24/7 crypto, and international equities (LSE/JPX).
2. **Resolves the right calendar per symbol** from bare ticker strings (no instrument metadata exists today), via heuristics + an explicit per-symbol override.
3. Is **consumed everywhere market state matters**, not just the two places that gate on it today: observer fires, trigger evaluation, snapshot capture, the analytics leaderboard, and the UI.
4. Handles **holidays and half-days (early closes) correctly** across all of the above, including a new schedule mode that self-adjusts to a day's actual close.

**Non-goals.**

- Pre/post-market *trading* semantics. We model session phases (so we can label "pre-market" / "post-market"), but the open/closed **gate** remains the regular session, matching today's behavior.
- Any broker write path (the dashboard stays observational).
- Backfilling instrument metadata from a data vendor. Resolution is heuristic + manual override by design (see §4, Decision 3).
- M10 feature parity for non-Claude providers (out of scope, as elsewhere).

## 2. Background — Current State & Gaps

Holiday handling **exists today but is narrow**:

- `apps/observer/services/market_hours.py` wraps `pandas-market-calendars` with the **NYSE (`XNYS`)** calendar. `is_market_open(at)` is holiday- and half-day-aware (it reads the calendar's actual `market_open`/`market_close`); `market_status(at)` returns `{is_open, next_open, next_close}` for the UI bell.
- It is wired into exactly **two** call sites:
  - `apps/observer/services/run.py:39` — `if sched.market_hours_only and not is_market_open(): skip`.
  - `apps/triggers/tasks.py:39` — a **global** gate at the top of `evaluate_triggers()` that skips *all* trigger evaluation when NYSE is closed.
- `apps/observer/views.py:89` exposes `market_status_view` → `GET /api/observer/market-status`.

**Confirmed gaps** (from code reading):

1. **Single-calendar.** Everything assumes NYSE. Crypto/futures/bonds/intl symbols get NYSE hours, which is wrong (e.g., crypto is never "closed").
2. **No instrument metadata.** `OHLCBar`, `OptionChainSnapshot`, `NewsItem` (`apps/market/models.py`) and `WatchlistSymbol` (`apps/profiles/models.py`) store only a bare `ticker` CharField — there is nothing to derive a calendar from. A resolution layer is required.
3. **Snapshots have no market awareness.** `apps/snapshots/services/__init__.py::capture_for_existing` never consults market state; `Snapshot` (`apps/snapshots/models.py`) has only `captured_at`. A holiday/after-hours capture is silently stale.
4. **Analytics forward-returns are wall-clock.** `apps/analytics/services/leaderboard.py::_forward_return_pct` computes `at + timedelta(hours=forward_hours)` and `_nearest_bar_close` grabs the nearest bar `<= target + 1h`. A Friday-afternoon capture's "24h return" silently reads back a stale Friday-close bar instead of reporting that the market was closed.
5. **Trigger gate is global, not per-instrument.** A crypto trigger cannot fire outside NYSE hours.
6. **Edge bug.** `is_market_open` / `market_status` key the schedule lookup on `now.date()` (the **UTC** date). Near midnight UTC this can select the wrong session day for `market_status`'s `next_open` computation. To be fixed during generalization.

## 3. Key Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Where the service lives | **Extend `apps/market`** with a `calendar/` package + `CalendarOverride` model | `apps/market` already owns market-domain data (`OHLCBar`, chains, Schwab client) and deals in tickers. Calendars + per-symbol overrides belong with it. No `INSTALLED_APPS` churn. Alternative considered: a new `apps/calendars` app — cleaner boundary but more wiring for what is market-domain logic. |
| 2 | Relative-to-close firing | **Beat poller** (`fire_close_relative_schedules`, every minute) | Computes the day's *actual* close on the schedule's calendar and fires once within `[close−offset, close−offset+1m)`. Robust to half-days and DST with no cron mutation. Alternative considered: nightly cron rewrite — more moving parts, fragile around DST. |
| 3 | Symbol→calendar resolution | **Heuristics + explicit override** | Precedence: override → pattern heuristic → NYSE default. Works out-of-the-box, no external lookups, always correctable. Overrides surfaced in the Settings hub. |
| 4 | Snapshot on a closed market | **Always capture + label as-of** | Stamp market state + "as-of last close" on the snapshot and surface it to the AI payload and UI. Never blocks (fits the observational nature of the tool). |
| 5 | Forward-return horizon | **Trading-day horizons** | Reinterpret `forward_hours` as trading sessions on the instrument's calendar; require a real bar near the target session, else report an honest coverage gap (`None`) — never a stale fill. |
| 6 | Observer/trigger gate | **Resolve from watchlist** | Gate each schedule/trigger on the calendar(s) of the symbols it watches — open if **any** watched market is open. Equity watchlists keep NYSE hours; crypto/futures stay active off-hours. |

## 4. Architecture — Core Service (`apps/market/calendar/`)

New package `backend/apps/market/calendar/`:

```
apps/market/calendar/
  __init__.py        # public exports: market_state, is_open, any_market_open,
                     #   calendar_for, add_trading_days, session_close_on, MARKETS
  registry.py        # market-key → mcal calendar id; cached get_calendar() at import
  resolve.py         # calendar_for(symbol) -> market_key  (override → heuristic → default)
  sessions.py        # market_state / is_open / any_market_open / trading-day math
  heuristics.py      # pattern rules (futures roots, crypto suffixes, .L/.T)
```

> Note: the directory is `calendar/` (a package) and **must not** shadow the stdlib `calendar` module at import sites — internal code imports `from apps.market.calendar import ...`, never bare `import calendar` from within the package without an absolute path. Verify no stdlib `calendar` use inside the package.

### 4.1 Registry (`registry.py`)

A `MARKETS` mapping from a logical **market key** to a `pandas-market-calendars` identifier. Calendars are fetched via `mcal.get_calendar(...)` and **cached at import** (as today):

| Market key | mcal id (verify exact id at impl) | Notes |
|------------|-----------------------------------|-------|
| `us_equity` | `NYSE` (`XNYS`) | Default. NYSE/NASDAQ share the holiday + half-day schedule. |
| `us_bond` | `SIFMA_US` | Bond market: open some days equities are closed (Columbus Day, Veterans Day); different early closes. |
| `cme_futures` | `CME_Equity` | Index futures (`/ES`, `/NQ`). Near-24h with a daily maintenance break (`break_start`/`break_end`). |
| `cfe_futures` | `CFE` (CBOE Futures) | VIX futures (`/VX`). |
| `crypto` | `24/7` | Always open; every calendar day is a trading day. |
| `lse` | `LSE` | London. |
| `jpx` | `JPX` (or `XTKS`) | Tokyo. |

`get_market_calendar(market_key)` returns the cached calendar; unknown key → `us_equity`.

### 4.2 Resolution (`resolve.py` + `heuristics.py`)

```python
def calendar_for(symbol: str) -> str:  # returns a market key
    # 1. explicit override (CalendarOverride table, cached)
    # 2. pattern heuristic (heuristics.classify)
    # 3. default -> "us_equity"
```

Heuristic rules (ordered, first match wins), operating on the upper-cased symbol:

- **Futures:** leading `/` or a known root → futures. `VX`/`/VX` → `cfe_futures`; `ES`,`NQ`,`RTY`,`YM`,`CL`,`GC`,`ZB`,… → `cme_futures`.
- **Crypto:** suffix `-USD`/`-USDT`/`-USDC` or a known base set (`BTC`,`ETH`,…) → `crypto`.
- **International:** suffix `.L` → `lse`; `.T` → `jpx`.
- **Default:** `us_equity` (covers plain equities/ETFs and index symbols like `$VIX`/`SPX`, which are quoted during equity hours).

`calendar_for` **never raises**; an unrecognized symbol logs once (deduped) and falls back to `us_equity`. The override lookup is cached (per-process, invalidated on `CalendarOverride` save/delete).

### 4.3 Session API (`sessions.py`)

All functions are timezone-aware **UTC** and accept an optional `at` (defaults to `timezone.now()`).

```python
def market_state(*, symbol: str | None = None, market: str | None = None,
                 at: datetime | None = None) -> MarketState
def is_open(*, symbol=None, market=None, at=None) -> bool
def any_market_open(symbols: Iterable[str], at=None) -> bool   # union; empty -> us_equity
def add_trading_days(market: str, anchor: datetime, n: int) -> datetime   # via valid_days
def session_close_on(market: str, on_date: date) -> datetime | None       # half-day aware
```

`MarketState` (a dataclass / typed dict) carries:

```
market_key, phase: "open"|"closed"|"weekend"|"holiday"|"half_day"|"premarket"|"postmarket",
is_open: bool, session_open, session_close, is_early_close: bool,
as_of,           # the most recent session close at/just before `at` (the "data is as-of" anchor)
next_open, next_close
```

**Implementation notes:**

- Build the schedule over a **±1-day window** around `at` (with `start='pre', end='post'` so phases can be derived) and select the session row whose `[market_open, market_close]` contains `at`. This fixes the `now.date()` UTC-edge bug (gap #6).
- `phase`: inside `[open,close]` → `open`; inside `[pre,open)` → `premarket`; inside `(close,post]` → `postmarket`; a session exists but `at` is outside it → `closed`; no session that day → `weekend` vs `holiday` (weekend by weekday, else `holiday`); a session whose close is earlier than the calendar's regular close → `is_early_close=True` (and `phase="half_day"` only when `at` is past the early close but before the normal close — otherwise `open`/`closed` as usual with `is_early_close` flagged).
- `crypto` (`24/7`): always `is_open=True`, `phase="open"`, no `as_of` staleness.
- `add_trading_days`: use `calendar.valid_days(anchor.date(), anchor.date()+buffer)` and index `n` sessions forward (buffer sized generously, e.g. `n*3+10` calendar days; crypto → every day counts).
- `any_market_open`: `True` if `is_open(symbol=s)` for any `s`; empty iterable → `is_open(market="us_equity")`.

### 4.4 Back-compat shim

`apps/observer/services/market_hours.py` becomes a thin re-export so existing imports keep working during migration:

```python
from apps.market.calendar import is_open as _is_open, market_state as _state
def is_market_open(at=None) -> bool: return _is_open(market="us_equity", at=at)
def market_status(at=None) -> dict:  # same {is_open, next_open, next_close} shape as today
    s = _state(market="us_equity", at=at); return {...}
```

Call sites in `run.py` and `triggers/tasks.py` are then **migrated** to the per-watchlist / per-trigger functions (§6). The shim remains for any incidental importers and tests.

## 5. Data Model & Migrations

1. **`apps/market` — `CalendarOverride`** (new):
   - `symbol = CharField(max_length=16, unique=True)` (upper-cased on save, like `WatchlistSymbol`)
   - `market_key = CharField(max_length=16, choices=MARKET_CHOICES)`
   - `note = CharField(blank, default="")`
   - `created_at`, `updated_at`
   - Migration + admin registration. Saving/deleting invalidates the resolution cache.
2. **`apps/snapshots` — `Snapshot.market_state`** (new): `JSONField(null=True, blank=True)`. Stores the at-capture market snapshot (see §6.1). Migration.
3. **`apps/observer` — `ObserverSchedule`** (new fields):
   - `fire_mode = CharField(choices=[("cron","Cron"),("relative_to_close","Relative to close")], default="cron")`
   - `close_offset_minutes = PositiveIntegerField(default=5)` (minutes **before** the actual close to fire)
   - Migration. Existing `market_hours_only` field is reused (now resolved per-watchlist).

## 6. Per-Surface Wiring

### 6.1 Snapshots (`apps/snapshots`)

- In `capture_for_existing` (after sections are filled, before `snap.save()`), compute `market_state`:
  - Collect the snapshot's representative tickers: keys of the `quotes` section if present, else `watchlist_tickers`, else `ohlc_ticker`.
  - Resolve each to a market key; dedup. Build `snap.market_state = { "captured_at": <iso>, "any_open": bool, "markets": { market_key: {phase, is_open, is_early_close, session_close, as_of} }, "representative_tickers": [...] }`.
  - Empty/positions-only snapshot → `us_equity` as the representative market.
- `apps/snapshots/serializer.py::serialize_for_ai` prepends a one-line **market-state banner** when no representative market is open, e.g.:
  `> Market state at capture: US equities CLOSED (holiday). Data is as-of last close 2026-05-22 16:00 ET.`
  (Open markets get no banner, or a terse "markets open" line — keep token cost minimal.)

### 6.2 Analytics leaderboard (`apps/analytics/services/leaderboard.py`)

- `provider_leaderboard(forward_hours=N)`: keep the param, document its trading-day reinterpretation. Compute `sessions = max(1, round(forward_hours / 24))`.
- Rewrite `_forward_return_pct(ticker, at, forward_hours)`:
  - `market = calendar_for(ticker)`
  - `t0 = _nearest_bar_close(ticker, at, tolerance)` (the capture-time bar)
  - `target = session_close_on(market, add_trading_days(market, at, sessions).date())`
  - `t1 = _nearest_bar_close(ticker, target, tolerance)` **requiring** the bar's `ts` be within `tolerance` (e.g., ±1 session / configurable hours) of `target`; otherwise `None`.
  - Return `None` when either endpoint is missing or out of tolerance → counts as a coverage gap (existing `coverage_pct` logic already handles `None`).
- `_nearest_bar_close` gains a `tolerance` and returns `None` when the nearest bar is outside it (kills the silent stale-fill).
- The leaderboard docstring + the `forward_hours` semantics note are updated.

### 6.3 Observer gate (`apps/observer/services/run.py`)

Replace line 39:

```python
from apps.market.calendar import any_market_open
if sched.market_hours_only and not any_market_open(sched.default_watchlist_tickers):
    log.info("observer %s skipped: all watched markets closed", schedule_id); return None
```

Empty `default_watchlist_tickers` → `any_market_open([])` → `us_equity` (unchanged behavior for equity users).

### 6.4 Trigger gate (`apps/triggers/tasks.py`)

- Add `tickers_in_condition(condition: dict) -> set[str]` (walk the `all/any/not` tree, collect leaf `ticker` values) — in `apps/triggers/dsl.py` (alongside `validate_condition`).
- Remove the **global** gate at the top of `evaluate_triggers`. Instead, inside the per-trigger loop, skip a trigger when **none** of its tickers' markets are open:

```python
for trigger in triggers:
    if not any_market_open(tickers_in_condition(trigger.condition)):
        continue
    ...
```

- Optimization: build `metrics.build_snapshot(...)` only over the set of triggers that passed the gate (skip the whole tick early if none are live, preserving the current "market_closed" fast-path semantics for an all-equity setup).

### 6.5 Relative-to-close mode (`apps/observer`)

- New beat task `observer.fire_close_relative_schedules` in `apps/observer/tasks.py`, scheduled `crontab(minute="*")` in `config/celery.py` `beat_schedule`, and added to the **explicit task list** in `config/celery.py` (per the project convention that tasks are not autodiscovered).
- Logic per enabled `ObserverSchedule` where `fire_mode="relative_to_close"`:
  - Resolve the schedule's **close calendar** = `calendar_for(first(default_watchlist_tickers))`, default `us_equity`.
  - `close = session_close_on(market, now.date())`. If `None` (non-trading day) → skip.
  - Fire window: `[close − close_offset_minutes, close − close_offset_minutes + 1 minute)`.
  - **Once-per-day guard:** skip if `last_fired_at` is on the same calendar day (in the calendar's tz). On fire, call the existing `run_observer_task.delay(schedule_id)` path (which stamps `last_fired_at`).
- `cron`-mode schedules are untouched (still driven by their `PeriodicTask`). The `market_hours_only` gate inside `run_observer` still applies to both modes.
- Beat downtime may cause a missed day for a relative schedule — documented & acceptable (no catch-up).

## 7. API Endpoints

- **`GET /api/market/calendar-status`** (new, `apps/market`): returns market state for a set of markets/symbols. Query: `?symbol=BTC-USD` or `?market=crypto` (repeatable) → `{ markets: { market_key: {is_open, phase, next_open, next_close, is_early_close} } }`. No args → the default set (`us_equity` + any market keys present in `CalendarOverride`). This backs the TopNav badge.
- **`/api/market/calendar-overrides`** (new, DRF `ModelViewSet`): CRUD for `CalendarOverride`. Read/write `symbol`, `market_key`, `note`.
- **`GET /api/observer/market-status`** (existing): kept as-is for back-compat (NYSE), now delegating to the shim.

URL include ordering: register `/api/market/calendar-status` and `/api/market/calendar-overrides` under the existing `apps.market` include; keep specific prefixes ahead of generic `/api/` includes (per the documented ordering gotcha).

## 8. Frontend Surfaces

| Surface | File | Change |
|---------|------|--------|
| Market status badge | `frontend/src/components/layout/TopNav.tsx` + new `MarketStatusBadge.tsx` + new `hooks/useMarketStatus.ts` | Consume `/api/market/calendar-status`; show a small open/closed dot with a per-market tooltip. (Endpoint type `MarketStatus` already stubbed in `api/observer.ts`; add multi-market type in `api/market.ts`.) |
| Closed-capture banner | `frontend/src/pages/SnapshotComposerPage.tsx` | Non-blocking banner: "Market closed — snapshot will be labeled as-of last close." Reads `useMarketStatus` for the selected watchlist's symbols. |
| Schedule form | `frontend/src/pages/SchedulesPage.tsx` + `api/observer.ts` (`ObserverSchedule`, `CreateScheduleBody`) | Add `fire_mode` select + `close_offset_minutes` input (shown when `relative_to_close`). |
| Settings override card | new `frontend/src/components/SymbolCalendarOverridesCard.tsx` added to `frontend/src/pages/Settings.tsx` | List/add/edit/delete overrides (symbol → market dropdown) via `/api/market/calendar-overrides`. Plugs into the Settings hub redesign. |
| Leaderboard label | `frontend/src/components/analytics/ProviderLeaderboardCard.tsx` + `hooks/useAnalytics.ts` | Label the horizon as trading-day-aware; clarify that "Cov" is a real-bar coverage gap. |

Frontend primitives (`Skeleton`, `EmptyState`, `ErrorBoundary`, `Toasts`) and the existing API client (`api/client.ts`) are reused. New hooks follow the React Query patterns in `hooks/`.

## 9. Error Handling & Edge Cases

- **Unknown/garbled symbol** → `us_equity` default; never raises; logs once.
- **mcal raises for a date** → treat as closed; log; do not crash a capture/tick.
- **Crypto 24/7** → always open; `add_trading_days` counts every calendar day; no staleness banner.
- **Half-days** → handled natively by mcal's actual `market_close`; `is_early_close` surfaced; relative-to-close uses the real (early) close.
- **DST / near-midnight UTC** → fixed by the window-select in `market_state` (§4.3); all timestamps UTC.
- **Relative-to-close double-fire** → once-per-day guard via `last_fired_at`; beat downtime may skip a day (documented).
- **Back-compat** → `market_hours.py` shim + `/api/observer/market-status` preserved; existing tests in `apps/observer/tests/test_market_hours.py` continue to pass (NYSE).

## 10. Testing Strategy

**Unit (pure logic; `pytest.mark.parametrize` + `freezegun`):**
- `calendar_for` heuristics: table of symbol → expected market key (futures roots, crypto suffixes, `.L`/`.T`, plain equities, override wins).
- `market_state` across weekend / holiday / half-day / pre-market / post-market / regular for `us_equity`; `crypto` always-open; `cme_futures` break handling.
- `add_trading_days` spanning a holiday and a weekend; `session_close_on` returns early close on a half-day; `None` on a non-trading day.
- `any_market_open` union semantics; empty → us_equity.
- `tickers_in_condition` over nested `all/any/not` DSL.
- Relative-to-close window math on a normal day and an early-close day.
- Forward-return: trading-day target + coverage gap (`None`) when no bar near target; correct % when bars exist.

**Integration (real PG / fakeredis / Celery eager):**
- Observer gate: skip when all watched markets closed; fire when any open (crypto watchlist off-hours).
- Trigger per-trigger gating: equity trigger skipped off-hours, crypto trigger evaluated.
- Snapshot `market_state` stamped; `serialize_for_ai` banner present when closed.
- `fire_close_relative_schedules`: fires once within the early-close window on a half-day; no double-fire.
- `CalendarOverride` CRUD + cache invalidation changes resolution.

**E2E / visual / a11y (six-lane suite) + frontend vitest:**
- TopNav market badge open/closed states (visual).
- Snapshot closed-capture banner (ui).
- Settings override card add/edit (ui + a11y).
- Schedule relative-to-close form fields (ui).
- Leaderboard trading-day label (visual).
- vitest: `useMarketStatus`, `MarketStatusBadge`, `SymbolCalendarOverridesCard`, schedule-form additions.

## 11. Build Order (Phases)

1. **Foundation** — `apps/market/calendar/` (registry, resolve, heuristics, sessions) + back-compat shim. Unit tests. No behavior change to call sites yet.
2. **Overrides** — `CalendarOverride` model + migration + `/api/market/calendar-overrides` + cache invalidation + Settings card.
3. **Backend wiring** — snapshot `market_state` + serializer banner; analytics trading-day forward returns; observer gate; trigger per-trigger gate (+ `tickers_in_condition`).
4. **Relative-to-close** — `ObserverSchedule` fields + beat task + celery registration + schedule-form UI.
5. **Frontend status surfaces** — `/api/market/calendar-status` + `useMarketStatus` + TopNav badge + snapshot banner + leaderboard label.
6. **Tests throughout** — each phase lands with its unit/integration tests; E2E/visual at the end of the phase that introduces the surface.

Each phase is independently shippable and leaves the app green (`make check`).

## 12. Open Questions / Future

- Exact mcal calendar identifiers for `SIFMA_US`, `CFE`, `LSE`, `JPX`, `24/7` are pinned in `registry.py` at implementation (verified against the installed `pandas-market-calendars` version inside the container).
- Per-symbol override management could later be enriched by Schwab `assetType`/`exchange` auto-suggestions (Decision 3 alternative) — deferred.
- Non-Claude provider parity and pre/post-market gating remain out of scope.
