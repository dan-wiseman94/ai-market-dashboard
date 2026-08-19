# Snapshot 24-hour data window — design

- **Date:** 2026-06-25
- **Status:** Shipped (amended 2026-08-19 — see §3.1)
- **Scope:** `apps.market` (OHLC service), `apps.snapshots` (capture services, model, views, serializers), `frontend` (composer/table/api types), OpenAPI schema.

## 1. Problem

Snapshot OHLC and news sections do not cover a consistent time window. For intraday
timeframes the OHLC section returns only the *latest trading session + 1h premarket*
(`fetch_ohlc_session`), so a capture taken at 9:45 a.m. shows ~2 hours and a weekend
capture shows stale Friday data. There is also a separate opt-in **overnight capture
mode** that produces yet another window (prior session open → now). News already
defaults to a 24h lookback but is widened/relabeled under overnight mode.

We want every snapshot to **always include roughly the last 24 hours of OHLC and news**,
regardless of capture time, and to retire the now-redundant overnight capture mode.

## 2. Requirements (decided)

1. **Target sections:** OHLC price bars and news.
2. **Window semantics — rolling 24h, never empty:** the window is `now − 24h → now`
   (extended-hours bars included), but when that window would be empty or thin (weekend,
   holiday, pre-market) it stretches back to the most recent session so there is always
   meaningful data.
3. **Timeframes:** the 24h window is the standard behavior for **intraday** timeframes
   (`1m`/`5m`/`15m`/`1h`). **Daily** (`1d`) keeps its fixed 60-bar count (24h of daily
   bars is a single bar). The **overnight capture mode is removed** — the 24h window
   subsumes it.
4. **Blended resolution for `1m` requests:** preserve 1-minute detail for the **current
   session**; coarsen the older portion of the 24h window to **5m** to keep bar counts /
   token cost sane.
5. **News:** always the 24h default; drop the overnight-specific lookback.

## 3. The window algorithm (union window)

For intraday OHLC the window is computed once per capture:

```
session_open = open of the most-recent session that has opened at/before now
               (pandas-market-calendars, 7-day lookback — same source as today)
start        = min(now − 24h, session_open)
end          = now
```

Bars are fetched with extended hours and clamped to `[start, end]`. The `min(...)` is
what guarantees "never empty/thin": when a bare 24h window would miss the most recent
session, `start` snaps back to `session_open`.

| Capture time | Window produced |
|---|---|
| Tue 2:00 p.m. (mid-session) | Mon 2 p.m. → Tue 2 p.m. — exactly 24h |
| Tue 4:30 p.m. (after close) | Mon 4:30 p.m. → Tue 4:30 p.m. — exactly 24h |
| Mon 6:00 a.m. (pre-market) | Fri 9:30 a.m. → Mon 6 a.m. — stretches to last session |
| Sun 8:00 a.m. | Fri 9:30 a.m. → Sun 8 a.m. |
| Sat 8:00 a.m. | Fri 8 a.m. → Sat 8 a.m. — ~24h (Fri premarket+session+after-hours) |

When the calendar lookup yields no session at all (calendar failure / empty schedule),
the function returns `[]`; the section still completes (see §8).

### 3.1 Blended resolution (`1m` requests only)

The union window is split at `session_open` (clamped into the window):

- **`[session_open, end]` → fetched at `1m`** (the current session, full detail)
- **`[start, session_open)` → fetched at `5m`** (older overnight / prior-session portion)

The two native-resolution fetches are clamped to their sub-windows and concatenated
(older → newer) into one monotonic series. Each segment is **persisted under its true
timeframe** — `_persist_bars(ticker, "5m", older)` and `_persist_bars(ticker, "1m",
recent)` — so `OHLCBar` rows (consumed by trigger backtests) stay correctly labeled.

Requests for `5m`/`15m`/`1h` are **not** blended: a single fetch covers the whole union
window at the requested timeframe. `1d` is unchanged (60-bar count).

**Weekend / pre-market edge case (intentional):** when `session_open` is the last real
session (e.g. Friday on a Monday pre-market capture), the 1m segment covers that whole
session through `now` and the 5m segment is empty. This is the faithful reading of "1m
for the current session." The token budget trims if the series is large.

**Amendment (2026-08-19) — shipped code differs; prefer it.** `market/services/ohlc.py`
does not split at `session_open` alone: the 1m tail is additionally capped at a fixed
recency window, `fine_start = max(start, session_open, end − _FINE_WINDOW)` with
`_FINE_WINDOW = 4h`. The 1m segment still never starts before the current session's
open, but a long session (a 23h futures session, or a pre-market capture reaching back
into the prior session) is coarsened to 5m beyond the newest ~4h — so the weekend /
pre-market edge case above does not ship as written (a whole session at 1m would emit
~1,000 bars).

## 4. Component changes

### 4.1 Market layer — `backend/apps/market/services/ohlc.py`

- **Add** `fetch_ohlc_24h(ticker, *, timeframe)`:
  - Computes the union window (§3) via a small session-open helper (refactor the calendar
    lookup currently inside `_session_window`).
  - `1m` → blended fetch + dual `_persist_bars` (§3.1). Other intraday timeframes → single
    windowed fetch. Returns the bar list (blended for `1m`).
  - Cache key `market:ohlc:{ticker}:{tf}:24h`, TTL `cache.ttl_for_kind(f"ohlc_{tf}")`
    (mirrors the existing session/overnight cache pattern; window depends on `now`, same
    as today).
  - **Free-provider fallback** (Schwab not connected): `fallback.alt_bars(ticker, timeframe,
    limit=N)` where `N` is a per-timeframe count sized to ~24h. Single-resolution at the
    requested timeframe — **not** blended (free providers are count-based; this matches the
    current session/overnight fallback behavior). Same degrade-or-raise as today.
- **Delete (dead after this change):** `fetch_ohlc_session`, `_session_window`,
  `_fetch_session_from_schwab`, `fetch_ohlc_overnight`, `_overnight_window`,
  `_fetch_overnight_from_schwab`. (Their only callers are the snapshot capture branches
  being replaced.)
- **Keep:** `fetch_ohlc` (fixed-count) — still used by charts, AI tools, trigger metrics,
  and the daily/`1d` snapshot branch. `_rows_from_candles`, `_persist_bars`,
  `_METHOD_BY_TIMEFRAME`, `SESSION_TIMEFRAMES` (or replace `SESSION_TIMEFRAMES` with an
  equivalent "intraday timeframes" set used by the section logic).

### 4.2 Snapshots capture — `backend/apps/snapshots/services/__init__.py`

- `_fetch_ohlc_section`: drop the `overnight` branch. Intraday → `fetch_ohlc_24h`; daily →
  `fetch_ohlc(..., bars=ohlc_bars)` unchanged. Payload gains `"window": "24h"` and, for the
  `1m` blend, `"coarse_timeframe": "5m"` (its presence signals the blend; the 5m→1m boundary
  is visible in the bar timestamps).
- `_fetch_news_section`: always `fetch_news(tickers)` (24h default). Remove the `overnight`
  branch and delete the `_overnight_news_lookback_hours` helper.
- Remove the `overnight` parameter from `capture`/`capture_for_existing` plumbing and the
  now-unused `as_of` overnight wiring (keep `as_of` only if used elsewhere — verify).

### 4.3 Serializer — `backend/apps/snapshots/serializer.py`

- `_render_ohlc`: replace the `window == "overnight"` header suffix with a `window == "24h"`
  suffix, e.g. `— last 24h (1m recent, 5m earlier)` when blended, else `— last 24h`.
- `_render_news`: drop the `window == "overnight"` branch; always title `## News (last 24h)`.
- `_ohlc_gap_note` is unchanged. Note: a 24h window legitimately contains overnight/weekend
  gaps, so the existing gap caveat may render — this already happened for overnight captures
  and is acceptable.

### 4.4 Remove the overnight capture flag

- **Model** `backend/apps/snapshots/models.py`: drop `overnight = models.BooleanField(...)`.
  - Migration `0014_remove_snapshot_overnight` (depends on `0013_snapshot_candidate_positions`):
    `RemoveField`. Reversible (re-add with `default=False, db_index=True`). On Postgres a
    column drop is a fast metadata operation.
- **Views** `backend/apps/snapshots/views.py`: remove the `?overnight=true` listing filter
  (64–65), the `create` field (84), and the `capture_task` arg (99).
- **Tasks** `backend/apps/snapshots/tasks.py`: remove the `overnight` param and pass-through.
- **Capture pipeline couplings** `backend/apps/snapshots/services/__init__.py`: the flag has three
  further effects that disappear with it — all intended consequences of removing the mode:
  - It auto-added the `overnight` **board** section to `includes` and set `snap.overnight = True`
    (`capture_for_existing`). After removal, the board section is included only when the user
    explicitly lists `"overnight"` in `includes` (cleaner / explicit).
  - It computed `as_of` (from `market_state`) solely to widen the news lookback. `as_of` becomes
    dead and is dropped along with the overnight news branch.
  - It toggled the `quotes` section's `gap_context` (`fetch_quotes(..., gap_context=overnight)`).
    With the flag gone, quotes use the default `gap_context=False`. (The quotes renderer still
    shows gap columns when a payload happens to carry them — only the auto-toggle goes.)
- **Serializers** `backend/apps/snapshots/serializers.py`: remove `overnight` from both
  serializers (lines 40, 77).
- **Schema:** regenerate `backend/schema.yml` (`make schema`) and
  `frontend/src/api/schema.d.ts` (`pnpm gen:api`) — both are drift-gated.
- **Frontend:** remove the overnight toggle/column/filter usage in
  `frontend/src/pages/SnapshotComposerPage.tsx`, `frontend/src/pages/snapshots/SnapshotTable.tsx`,
  and `frontend/src/api/snapshots.ts`; check `frontend/src/pages/BriefingPage.tsx`. Update
  the affected FE tests (`SnapshotComposerPage.test.tsx`, `useCreateSnapshot.test.tsx`,
  `api/observer.test.ts` if it references the field).

### 4.5 Kept — the unrelated overnight *board* section

The `overnight` **includes-section** (`overnight_board`, `_render_overnight`, `diff.py:92`,
`test_services_overnight_board.py`, `test_calendar_sessions.py`) is a different feature
(after-hours quote board) and is **not** touched.

## 5. Payload shape

OHLC section payload (blended `1m` example):

```json
{
  "data": {
    "ticker": "NVDA",
    "timeframe": "1m",
    "window": "24h",
    "coarse_timeframe": "5m",
    "bars": [ {"ts": "...", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}, ... ]
  }
}
```

Non-blended intraday (`5m`/`15m`/`1h`): same shape without `coarse_timeframe`.
Daily (`1d`): unchanged (no `window`).

## 6. Data flow

```
POST /api/snapshots/  →  Snapshot row  →  capture_task.delay(...)  (no overnight arg)
  capture_for_existing → loop over includes
    "ohlc"  → _fetch_ohlc_section → fetch_ohlc_24h (union window; 1m blended) → payload
    "news"  → _fetch_news_section → fetch_news(tickers, lookback_hours=24)    → payload
  serialize_for_ai(snap) renders sections (no time filtering; token-budget trim only)
```

## 7. Error handling

Unchanged section contract: a raising fetcher is caught and the section is marked
`failed`; partial snapshots are acceptable. The "never empty" rule is about *window
selection*, not exceptions — if the calendar lookup returns nothing, `fetch_ohlc_24h`
returns `[]` and the section completes empty rather than raising.

## 8. Testing

- **New unit tests** (`apps/market/tests`): `fetch_ohlc_24h` window math for the four §3
  edge cases, with `now` injected and the calendar + Schwab/fallback mocked; assert bars
  clamped to `[start, end]`. Blend test: `1m` request produces a 5m older segment + 1m
  current-session segment, persisted under the correct timeframes; weekend/pre-market case
  yields an empty 5m segment.
- **Update** (`apps/snapshots/tests`): `_fetch_ohlc_section` / `_fetch_news_section` no
  longer branch on overnight; serializer label assertions (`last 24h`).
- **Remove** (after confirming each is capture-flag, not board, related):
  `test_overnight_model.py`, `test_overnight_news_lookback.py`, `test_capture_overnight.py`,
  `test_serializer_overnight.py`, `test_services_ohlc_overnight.py`. Verify
  `test_diff_overnight.py` targets the board section (keep) vs the flag (remove).
- **N+1 / query budgets:** unaffected (no new aggregations).
- **Gates:** `make schema` + `pnpm gen:api` (drift), then `make check`.

## 9. Out of scope

- The **chart-image render** keeps its existing fixed-bar window (it is a visual, separate
  from the OHLC data section).
- Daily (`1d`) snapshot behavior (60-bar count) is unchanged.
- The `_ohlc_gap_note` heuristic is unchanged.

## 10. Risks / notes

- Removing the `overnight` model field drops the `?overnight=true` listing filter — an
  accepted trade-off (the mode no longer exists). Any saved client query using it will
  simply ignore the param after removal.
- Migration touches a `db_index=True` column; the migration-safety gate (squawk) runs on
  migration PRs — a plain `RemoveField` is expected to pass.
- Blended `1m` series mixes resolutions; downstream consumers read bars by `ts` only, so
  monotonic ordering (and no duplicate `ts` at the 5m→1m boundary) is the invariant to preserve.
- Removing the overnight flag also turns off the `quotes` `gap_context` auto-toggle and the
  auto-add of the overnight board section. Both are intended (the mode is gone), but they are
  user-visible: a capture that previously set `overnight=true` to *also* get the board must now
  list `"overnight"` in `includes`.
- The free-provider fallback (Schwab not connected) is count-based and single-resolution: it
  returns recent bars at the requested timeframe sized to ~24h and is **not** blended. This
  matches today's session/overnight fallback behavior.
