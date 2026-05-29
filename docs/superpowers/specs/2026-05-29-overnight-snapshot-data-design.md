# Overnight snapshot data (pre-market enrichment) — design

**Date:** 2026-05-29
**Status:** Approved (pending spec review)
**Topic:** An opt-in **"overnight mode"** for snapshot capture that, when enabled, enriches the capture with extended-hours / overnight data so a pre-market snapshot reflects last night and this morning instead of yesterday's regular session. Four behaviors: an **overnight OHLC window**, **quote gap context**, an **overnight news window**, and a new **futures / overseas board** section.

## Problem

The capture pipeline already *labels* a snapshot's session — `snap.market_state.phase` can equal `"premarket"` / `"postmarket"` (`apps/market/calendar/sessions.py`) — but the data it gathers pre-market silently lags a full day:

1. **OHLC selects yesterday's session pre-market.** `_fetch_ohlc_session` (`apps/market/services/ohlc.py:105`) requests `need_extended_hours_data=True`, but `_session_window` (`ohlc.py:75`) picks "the latest session that has *already opened*" (`if o <= now`) and clamps the end to `min(chosen_close, now)`. Before 9:30 ET today's open hasn't happened, so it chooses **yesterday's** session and clamps to yesterday's 4pm close. A pre-market capture therefore shows yesterday's regular session and drops last night's after-hours, the overnight tape, *and* this morning's pre-market — despite requesting extended-hours data. (The same clamp drops post-market bars after 4pm; pre-market is the headline case.)
2. **Quotes carry no overnight context.** `_fetch_from_schwab` (`apps/market/services/quotes.py:28`) maps only 7 regular-session fields (`last/bid/ask/volume/high/low/pct_change`). There is no prior close, no gap %, no "this is a pre-market print" marker — so even when `last` *is* an extended-hours price, the AI cannot interpret it as one or measure the gap.
3. **News is a rolling 24h window**, not anchored to the overnight session, so "what broke since the close" is mixed with stale daytime items.
4. **There is no overnight board.** A pre-market trader's first read is index futures (ES/NQ) and overseas cash indices; the dashboard captures neither.

These are all capture-time data gaps. The fix is additive section work behind a single opt-in, reusing existing fetch patterns.

## Non-goals (YAGNI)

- **Not automatic / phase-gated.** Overnight mode is an explicit per-capture opt-in (a persisted boolean), *not* auto-enabled when `phase == "premarket"`. This keeps the shared `capture()` path (observer / trigger / briefing) provably unchanged. (Auto-on-phase was considered and declined during brainstorming.)
- **Not a default-behavior fix.** The latent OHLC clamp bug is *not* fixed for ordinary captures; the corrected window lives only on the overnight path. (Changing default capture would alter observer/trigger/briefing output.)
- **No streaming / live overnight feed.** A snapshot is a point-in-time capture; overnight mode widens what it pulls, it does not subscribe.
- **No new credential or data provider.** Futures and overseas indices ride the existing Schwab client. Overseas-index symbol coverage on Schwab is partial; unresolved symbols are omitted, not sourced elsewhere.
- **No per-user board configuration UI.** The board symbol set is a curated module constant (editable in code), mirroring `SECTOR_ETFS` / `CONTEXT_SYMBOLS`.

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Opt-in mechanism | Persisted boolean `Snapshot.overnight` + composer toggle | Explicit "mode"; filterable/badgeable in the new `/snapshots` browser; clean reads. Chosen over a magic section-in-`includes` (implicit cross-section coupling) and over an always-on auto-fix (changes the shared capture path). |
| Scope of "overnight data" | All four: OHLC window, quote gap context, overnight news, futures/overseas board | User-selected (all four). |
| Futures/overseas set | US index futures (ES/NQ/YM/RTY) + vol/rates (/VX, /ZN) + overseas cash (best-effort) | User-selected (all three groups). |
| Board fetch pattern | Curated symbol set, per-symbol silent degrade | Verbatim reuse of the `breadth` `$ADVN/$TICK/...` pattern (`services/context.py`). |
| OHLC window anchor | From the *open* of the most-recently-closed session → now, extended hours, no close-clamp | Gives full prior-day context plus the overnight gap, not just the after-hours sliver. |
| OHLC default timeframe | Coarsen `1m` → `5m` on the overnight path | A ~17h+ 1m series is ~1000+ bars — blows the per-model token budget; 5m keeps it readable. `5m/15m/1h/1d` requests pass through unchanged. |
| Behaviors gated | Every behavior is dead unless `overnight=True` | Default payloads, token counts, and the shared capture path are byte-identical to today. |
| Board section kind | `"overnight"` | Most descriptive; coexists with the `Snapshot.overnight` flag in a different namespace (model field vs section kind). |

## Architecture

```
 SnapshotComposerPage  ── overnight toggle ──► POST /api/snapshots/  {..., overnight: true}
        │                                              │
        │                                   SnapshotViewSet.create()
        │                                   Snapshot(overnight=True)
        │                                   capture_task.delay(..., overnight=True)
        ▼                                              │
 capture_for_existing(snap, ..., overnight=True)       │
        │                                              ▼
        ├─ if overnight: includes += ["overnight"]  (persisted)
        │
        ├─ per-section loop (apps/snapshots/services/__init__.py):
        │     fetchers receive overnight=<bool> + as_of=<prior close from market_state>
        │
        │     quotes   → overnight ? fetch_quotes(..., gap_context=True) : fetch_quotes(...)
        │     ohlc     → overnight ? fetch_ohlc_overnight(tkr, tf')      : fetch_ohlc_session/ohlc(...)
        │     news     → overnight ? fetch_news(.., lookback_hours=since_close) : fetch_news(..)
        │     overnight→ overnight_board()   ← /ES /NQ /YM /RTY /VX /ZN + overseas (best-effort)
        │
        └─ as_of (prior close) computed via market_state(symbol=primary market) at the top of the overnight path
           (snap.market_state itself is built AFTER the loop, so fetchers cannot read it)
```

### 1. Model + capture wiring — `apps/snapshots/`

Add one column to `Snapshot` (`apps/snapshots/models.py`):

```python
overnight = models.BooleanField(default=False, db_index=True)
```

- **`SnapshotSection.KIND_CHOICES`** gains `("overnight", "Overnight board")` (choices-only `AlterField`; DB `varchar` unchanged).
- **`SnapshotViewSet.create()`** (`apps/snapshots/views.py:61`) reads `overnight = bool(data.get("overnight", False))`, sets it on the `Snapshot`, and passes `overnight=overnight` to `capture_task.delay(...)`.
- **`capture_task`** (`apps/snapshots/tasks.py`) gains an `overnight: bool = False` kwarg, forwarded to `capture_for_existing`.
- **`capture_for_existing(... , overnight: bool = False)`** (`services/__init__.py`):
  - When `overnight` and `"overnight"` not already in `snap.includes`: append it and persist (`update_fields=["includes"]`) so the board section is captured and surfaces in serialization/section-listing like any other.
  - Compute `as_of` once at the top of the overnight path via `market_state(symbol=<primary or first watchlist ticker, fallback "SPY">).as_of` (the most-recent prior session close), and pass it into the fetchers alongside `overnight`. **NOTE:** `snap.market_state` is populated *after* the section loop (`services/__init__.py:227`), so the fetchers cannot read it — `as_of` must be computed independently here.
  - Each `_FETCHERS` entry's signature gains `overnight` and `as_of` (they already accept `**_`, so only the four enriched fetchers read them).

`capture()` (the convenience wrapper) gains the same `overnight=False` kwarg and forwards it; default callers (observer/trigger/briefing) pass nothing → unchanged.

### 2. Overnight OHLC window — `apps/market/services/ohlc.py`

New `fetch_ohlc_overnight(ticker, *, timeframe)`:

- **Window** = `_overnight_window(ticker, at=now)`:
  - `last_close` = the most-recent session close at/before `now` (the `as_of` semantics from `market_state`).
  - `start` = the **regular open of that same session** (so the series includes the prior regular session for context).
  - `end` = `now` (never clamped to a session close).
  - Returns `None` only if no session is found in the lookback (→ fetcher returns `[]`).
- Fetches with `need_extended_hours_data=True`; **does not** clamp candles to `chosen_close` (the bug) — clamps only to `[start, end]`.
- Reuses `_rows_from_candles` + `_persist_bars` (history persistence is identical; trigger backtests benefit).
- **Timeframe coarsening:** the `ohlc` fetcher coarsens a `1m` request to `5m` on the overnight path (the composer doesn't expose a timeframe control, and 1m over the overnight window is always too many bars); `5m/15m/1h/1d` pass through unchanged.
- **Fallback:** if `_overnight_window` returns `None`, fall back to `fetch_ohlc_session` (today's behavior) so the section still produces something.

The `ohlc` fetcher (`_fetch_ohlc_section`) branches: `overnight → fetch_ohlc_overnight(ticker, timeframe=coarsened_tf)` else the existing session/fixed logic. Payload shape (`{data: {ticker, timeframe, bars}}`) is unchanged; `timeframe` reflects the coarsened value and the payload notes `"window": "overnight"`.

### 3. Quote gap context — `apps/market/services/quotes.py`

`fetch_quotes(tickers, *, gap_context: bool = False)`. When `gap_context`:

- Use a distinct cache key suffix (`:gap`) so gap vs non-gap payloads don't collide in the 5s cache.
- `_fetch_from_schwab` keeps the 7 fields and adds, from the Schwab `quote` / `regular` blocks:
  - `prior_close` ← `closePrice`
  - `regular_last` ← `regular.regularMarketLastPrice` (fallback: top-level `regularMarketLastPrice`)
  - `mark` ← `mark`
  - `security_status` ← `securityStatus`
  - `gap_pct` = `(last - prior_close) / prior_close * 100` when both present, else `None`
- All added fields are `None`-tolerant (Schwab omits some by asset type). Non-gap callers are byte-identical to today.
- **Schwab field names must be verified against a live quote response at implementation** (via schwab-py docs / a real call); the names above match Schwab's documented EQUITY quote schema.
- No per-quote `session` field is added: the phase is a snapshot-level property already carried by `snap.market_state.phase` (serialized into the AI payload and shown in the UI). Stamping a `session` key into the quotes payload would collide with `primary_ticker_from_quotes`, which derives the ticker from the *first* payload key — so the gap context stays strictly per-ticker numeric fields.

`fetch_market_context()` (`services/context.py`) is **not** changed (breadth stays regular-session); only the per-ticker `quotes` section gains gap context, to bound scope and token growth.

### 4. Overnight news — `apps/snapshots/services/__init__.py` + `services/news.py`

The `news` fetcher, when `overnight` and `as_of` is present:

- `since_close_hours = ceil((now - as_of).total_seconds() / 3600)`, clamped to `[1, 48]`.
- `fetch_news(tickers, lookback_hours=since_close_hours)`.
- Payload becomes `{"items": [...], "window": "overnight", "since": as_of.isoformat()}` (today's shape is `{"items": [...]}`; the extra keys are additive and ignored by existing consumers).

`fetch_news` already supports `lookback_hours` and returns newest-first; no change to `news.py`.

### 5. Futures / overseas board — `apps/market/services/overnight.py` (new) + `overnight` section

New module `apps/market/services/overnight.py`:

```python
US_INDEX_FUTURES = ["/ES", "/NQ", "/YM", "/RTY"]   # front-month continuous
VOL_RATES        = ["/VX", "/ZN"]                  # VIX future, 10Y note
# Best-effort overseas cash indices. Schwab symbology for foreign indices is
# partial; unresolved symbols are dropped silently (same as breadth $ADVN/...).
OVERSEAS = ["$NIKK", "$HSI", "$UKX", "$DAX", "$SX5E"]   # verified/adjusted at impl

def overnight_board() -> dict:
    """{"futures": {...}, "vol_rates": {...}, "overseas": {...}} keyed by symbol,
    each value the gap-context quote dict. Per-symbol degrade: missing quotes drop out."""
```

- Implemented via `fetch_quotes(US_INDEX_FUTURES + VOL_RATES + OVERSEAS, gap_context=True)` (one batched Schwab call, 5s-cached), then grouped. Symbols Schwab won't quote return no `quote` block and are already skipped by `_fetch_from_schwab` — so they simply don't appear (no error).
- `normalize_symbol("/ES")` passes `/ES` through unchanged (not a `$`-alias, already upper) — futures symbols work without symbol-table changes. Overseas `$`-prefixed symbols also pass through; the listed symbols are a best-effort starting set, verified/adjusted against live Schwab responses at implementation, with unresolved ones removed.
- The `overnight` section fetcher: `lambda **_: {"data": overnight_board()}`. Independent of the watchlist.

### 6. Serialization, diff, browser

- **`SnapshotSerializer` + `SnapshotListSerializer`** (`apps/snapshots/serializers.py`): add `overnight = serializers.BooleanField(read_only=True)`. The list serializer's `section_kinds` will naturally include `"overnight"`.
- **`SnapshotViewSet.get_queryset()`**: add an optional filter — `if p.get("overnight") in ("true","1"): qs = qs.filter(overnight=True)`.
- **`diff_sections`** (`apps/snapshots/diff.py`): add a `_diff_overnight(prev, curr)` branch reporting notable net-% / gap moves per board line (cap to top movers; ignore sub-threshold), tolerant of bad shapes via the existing `_as_dict` invariant (the diff never raises). Low priority relative to the capture work; the board otherwise diffs as opaque JSON.

### 7. Frontend

- **`SnapshotComposerPage.tsx`**: an **"Overnight (pre-market)"** toggle near `SnapshotSectionPicker`. State `overnight: boolean` (default false), sent in the create body. When on, render a one-line hint: *"OHLC, quotes, and news shift to extended hours; adds a futures + overseas board."* The `overnight` board is auto-added server-side, so it is **not** a checkbox in the section picker (avoid double-control).
- **Snapshot detail** (the existing snapshot view / `SnapshotCostPage` neighbor): a renderer for the `overnight` board section — three small grouped tables (Futures / Vol & rates / Overseas) with symbol · last · gap %. Reuse `EmptyState` when a group is empty.
- **`/snapshots` browser** (Snapshot Intelligence work on this branch): an **"overnight"** badge on rows where `overnight === true` and an `overnight` filter chip wired to `?overnight=true`.
- **API client** (`frontend/src/api/snapshots.ts`): the create payload type gains `overnight?: boolean`; list/filter types gain the `overnight` field + filter param.
- **TS interfaces** use the exact serializer keys (`overnight`, board payload shape) per the repo's `*_id`/verbatim-key convention.

### 8. Mocks & tests

- **Mock client** (`apps/market/schwab_client.py` `_MockClient.get_quotes`): add `closePrice`, `mark`, `securityStatus`, and a `regular` block to the canned quote so gap-context + board tests (and the E2E lane under `MOCK_EXTERNAL`) exercise real field-mapping rather than all-`None`. The mock's `__getattr__` already returns empty candles for any OHLC method, so `fetch_ohlc_overnight` is covered (returns `[]`, exercises the fallback path).
- **Unit:**
  - `_overnight_window`: pre-market `now` → spans prior session open → now (parametrized: pre-market, mid-session, post-market, weekend/holiday, no-data → `None`).
  - quote gap mapping: `gap_pct` math; all fields `None`-tolerant; `gap_context=False` payload identical to today.
  - overnight news lookback computed from `as_of`; clamp bounds; fallback to 24h when `as_of` absent.
  - `overnight_board()` grouping + per-symbol degrade (symbols with no `quote` block dropped).
  - serializer exposes `overnight`.
- **Integration:** `capture_for_existing(overnight=True)` → appends `"overnight"` to includes, creates the board section, widens OHLC (timeframe coarsened), tags news `window=overnight`, stamps `session` on quotes; a default capture is byte-identical to today (regression guard).
- **Frontend (`vitest`):** composer toggle sends `overnight: true`; board-section renderer (loading/empty/populated); browser badge/filter.
- **E2E (`ui` lane):** `e2e/ui/test_snapshots_overnight_gold.py` — toggle overnight → capture → detail shows the board under `MOCK_EXTERNAL`.

### 9. Ops & migrations

- `apps/snapshots/migrations/`: (a) `AddField Snapshot.overnight` (BooleanField default False, indexed — reversible `RemoveField`); (b) choices-only `AlterField SnapshotSection.kind` (no DB change). Both reversible, no destructive ops, no locking concern at single-user scale.
- **No new Celery task or beat entry** — reuses `capture_task`, so **no `worker`/`beat` restart**.
- No new dependency, credential, or external service. Token growth (board + wider OHLC + gap fields) is bounded by the existing `token_budget.py` trim + coarsened timeframe, and recorded per-section by `stamp_payload_tokens`.

## Implementation order (for the plan)

1. `Snapshot.overnight` field + `AddField` migration; `SnapshotSection.kind` choices `AlterField`; serializer `overnight` field + `?overnight=` filter + tests.
2. Capture wiring: `overnight` kwarg through `views.create` → `capture_task` → `capture`/`capture_for_existing`; append `"overnight"` to includes; compute/thread `as_of`; default-capture regression test.
3. `fetch_ohlc_overnight` + `_overnight_window` + timeframe coarsening + fallback + tests.
4. `fetch_quotes(gap_context=True)` mapping + mock-client field additions + `session` stamping + tests.
5. Overnight news lookback in the `news` fetcher + tests.
6. `apps/market/services/overnight.py` `overnight_board()` + `overnight` section fetcher + tests.
7. `_diff_overnight` branch + parametrized tests.
8. Frontend: composer toggle, board renderer, browser badge/filter, API-client types, vitest coverage.
9. E2E `test_snapshots_overnight_gold.py`.

Steps 3–6 are independent of each other and depend only on steps 1–2; step 7 depends on 6; steps 8–9 depend on 1–6.
