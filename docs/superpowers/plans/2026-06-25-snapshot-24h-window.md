# Snapshot 24-hour data window — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every snapshot's OHLC and news sections always cover a rolling ~24-hour window, and remove the now-redundant overnight capture mode.

**Architecture:** A new `fetch_ohlc_24h` in the market layer computes a *union window* (`start = min(now−24h, most_recent_session_open)`, `end = now`, extended hours). For a `1m` request it blends the current session at 1m with the older portion coarsened to 5m. The snapshot capture pipeline calls it for intraday timeframes (daily unchanged); news always uses its 24h default. The `overnight` flag (model field, view param, listing filter, serializer field, FE toggle) and the dead session/overnight OHLC functions are removed.

**Tech Stack:** Django 5 + DRF, Celery, Postgres 16, pandas-market-calendars, pytest, React + TypeScript + vitest, openapi-typescript. Everything runs in Docker Compose.

## Global Constraints

- **All commands run in Docker.** Backend tests: `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (container WORKDIR is `/app/backend` — drop the `backend/` prefix). FE tests: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`. The dev stack must be up first: `make dev`.
- **Spec:** `docs/superpowers/specs/2026-06-25-snapshot-24h-window-design.md` — load-bearing; re-read the relevant section per task.
- **Section terminal state is `"done"`; only the parent `Snapshot` uses `"ready"`** — do not mix.
- **Always read snapshot image bytes via `image_store.read_image_bytes`** (not relevant here, but do not regress).
- **Worker landmine:** after editing a task module, runtime requires `docker compose restart worker beat`. Tests run Celery eager in `web`, so test runs are unaffected.
- **Quality gates** (`make check`): `ruff` + `mypy` (zero baseline, real gate) + `pytest` (CI uses `-p no:randomly`) + import-linter + FE `eslint`/`tsc`/`vitest` + OpenAPI drift gate (`backend/schema.yml` + `frontend/src/api/schema.d.ts`) + migration-safety (squawk) + coverage floors (backend 88).
- **Commit messages:** conventional (`feat(market):`, `refactor(snapshots):`, etc.), end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Work on branch `feat/snapshot-24h-window` (already created).
- **Two unrelated "overnight" concepts:** the `overnight` **capture flag** (removed here) vs. the `overnight` **board section** (`overnight_board`, `_render_overnight`, `diff.py`) — the board section and its tests (`test_services_overnight_board.py`, `test_diff_overnight.py`, `test_calendar_sessions.py`) are **kept untouched**.

---

## File Structure

**Market layer** — `backend/apps/market/services/ohlc.py`
- Add: `_most_recent_session_open`, `_union_window`, `_fetch_window_from_schwab`, `fetch_ohlc_24h`, `_fetch_24h_from_schwab`, constants `_COARSE_TIMEFRAME`, `_ALT_24H_LIMIT`, `INTRADAY_TIMEFRAMES`.
- Remove (Task 10): `fetch_ohlc_session`, `_session_window`, `_fetch_session_from_schwab`, `fetch_ohlc_overnight`, `_overnight_window`, `_fetch_overnight_from_schwab`, `SESSION_TIMEFRAMES`.
- Keep: `fetch_ohlc` (fixed-count — charts/tools/triggers/daily), `_rows_from_candles`, `_persist_bars`, `_METHOD_BY_TIMEFRAME`.

**Snapshots capture** — `backend/apps/snapshots/services/__init__.py`
- Rewrite `_fetch_ohlc_section`, `_fetch_news_section`; delete `_overnight_news_lookback_hours`; drop overnight plumbing from `capture` / `capture_for_existing` and the `quotes` fetcher.

**Snapshots serializer (markdown)** — `backend/apps/snapshots/serializer.py`
- `_render_ohlc` (24h header), `_render_news` (drop overnight label).

**Snapshots model / API / FE** — `models.py`, `views.py`, `tasks.py`, `serializers.py`, migration `0014`, `frontend/src/{api/snapshots.ts,pages/SnapshotComposerPage.tsx,pages/snapshots/SnapshotTable.tsx}`, `backend/schema.yml`, `frontend/src/api/schema.d.ts`.

---

## Task 1: Union-window math (`_most_recent_session_open`, `_union_window`)

**Files:**
- Modify: `backend/apps/market/services/ohlc.py`
- Test: `backend/apps/market/tests/test_services_ohlc_24h.py` (create)

**Interfaces:**
- Produces:
  - `_most_recent_session_open(ticker: str, *, at: datetime) -> datetime | None`
  - `_union_window(ticker: str, *, at: datetime | None = None) -> tuple[datetime, datetime, datetime] | None` returning `(start, end, session_open)`.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_services_ohlc_24h.py`:

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.ohlc import _most_recent_session_open, _union_window


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


# 2026-05-28 is a regular Thursday NYSE session (EDT, UTC-4): open 13:30 UTC.
# 2026-05-29 is a regular Friday session: open 13:30 UTC. 2026-06-01 is the next Monday.
_THU_OPEN = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)
_FRI_OPEN = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)


def test_most_recent_session_open_after_close_is_todays_open():
    now = datetime(2026, 5, 28, 21, 0, tzinfo=UTC)  # Thu 17:00 ET, after close
    assert _most_recent_session_open("SPY", at=now) == _THU_OPEN


def test_most_recent_session_open_premarket_is_prior_session():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)  # Fri 08:00 ET, before Fri open
    assert _most_recent_session_open("SPY", at=now) == _THU_OPEN


def test_union_window_midsession_is_rolling_24h():
    now = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)  # Thu 14:00 ET, mid-session
    start, end, session_open = _union_window("SPY", at=now)
    assert end == now
    assert session_open == _THU_OPEN
    assert start == now - timedelta(hours=24)  # 24h is before session open -> rolling


def test_union_window_stretches_back_to_session_over_weekend():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)  # Mon 08:00 ET, pre-market
    start, end, session_open = _union_window("SPY", at=now)
    assert session_open == _FRI_OPEN
    assert start == _FRI_OPEN  # now-24h (Sun) is after Fri open -> snaps back to session
    assert end == now
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_24h.py -v`
Expected: FAIL — `ImportError: cannot import name '_most_recent_session_open'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/apps/market/services/ohlc.py`, add after `_rows_from_candles` (around line 167):

```python
def _most_recent_session_open(ticker: str, *, at: datetime) -> datetime | None:
    """Regular open of the latest session that has opened at/before `at`. None when
    no session falls in the 7-day lookback (calendar failure / empty schedule)."""
    cal = get_market_calendar(calendar_for(ticker))
    try:
        sched = cal.schedule(
            start_date=(at - timedelta(days=7)).date(),
            end_date=(at + timedelta(days=1)).date(),
        )
    except Exception as exc:  # mcal can raise on odd ranges; treat as no data
        log.warning("ohlc.session_open schedule failed for %s: %s", ticker, exc)
        return None
    chosen = None
    for _idx, row in sched.iterrows():
        o = row["market_open"].to_pydatetime()
        if o <= at:  # keep the latest session already opened
            chosen = o
    return chosen


def _union_window(
    ticker: str, *, at: datetime | None = None
) -> tuple[datetime, datetime, datetime] | None:
    """(start, end, session_open) for the rolling 24h window, never thinner than the
    current session: start = min(at - 24h, session_open); end = at. None when no
    session falls in the lookback."""
    now = at or timezone.now()
    session_open = _most_recent_session_open(ticker, at=now)
    if session_open is None:
        return None
    start = min(now - timedelta(hours=24), session_open)
    return start, now, session_open
```

(`datetime`, `timedelta`, `UTC` and `timezone` are already imported at the top of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_24h.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/ohlc.py backend/apps/market/tests/test_services_ohlc_24h.py
git commit -m "$(printf 'feat(market): add union-window helpers for 24h OHLC\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: `fetch_ohlc_24h` — single-resolution intraday + free-provider fallback

**Files:**
- Modify: `backend/apps/market/services/ohlc.py`
- Test: `backend/apps/market/tests/test_services_ohlc_24h.py`

**Interfaces:**
- Consumes: `_union_window` (Task 1), `cache.get_or_fetch`, `cache.ttl_for_kind`, `fallback.alt_bars`, `SchwabNotConnectedError`, `_persist_bars`, `_rows_from_candles`, `_METHOD_BY_TIMEFRAME`.
- Produces:
  - `fetch_ohlc_24h(ticker: str, *, timeframe: str) -> list[dict]`
  - `_fetch_window_from_schwab(ticker, timeframe, start_dt, end_dt) -> list[dict]`
  - `INTRADAY_TIMEFRAMES: frozenset[str]`, `_COARSE_TIMEFRAME = "5m"`, `_ALT_24H_LIMIT: dict[str,int]`.

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/market/tests/test_services_ohlc_24h.py`:

```python
from apps.market.schwab_client import SchwabNotConnectedError  # noqa: E402
from apps.market.services.ohlc import fetch_ohlc_24h  # noqa: E402


@pytest.mark.django_db
def test_fetch_ohlc_24h_passes_union_window_and_clamps_extended_hours():
    start = datetime(2026, 5, 27, 18, 0, tzinfo=UTC)
    end = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)
    session_open = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)
    in_window = int(datetime(2026, 5, 28, 2, 0, tzinfo=UTC).timestamp() * 1000)
    out_of_window = int(datetime(2026, 5, 28, 19, 0, tzinfo=UTC).timestamp() * 1000)
    resp = MagicMock()
    resp.json.return_value = {
        "candles": [
            {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "datetime": in_window},
            {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "datetime": out_of_window},
        ]
    }
    client = MagicMock()
    client.get_price_history_every_five_minutes.return_value = resp
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="5m")
    assert len(bars) == 1  # out-of-window candle clamped away
    _, kwargs = client.get_price_history_every_five_minutes.call_args
    assert kwargs["need_extended_hours_data"] is True
    assert kwargs["start_datetime"] == start
    assert kwargs["end_datetime"] == end


@pytest.mark.django_db
def test_fetch_ohlc_24h_returns_empty_when_no_window():
    with patch("apps.market.services.ohlc._union_window", return_value=None):
        assert fetch_ohlc_24h("SPY", timeframe="5m") == []


@pytest.mark.django_db
def test_fetch_ohlc_24h_falls_back_to_alt_bars_when_schwab_not_connected():
    with (
        patch(
            "apps.market.services.ohlc.get_schwab_client",
            side_effect=SchwabNotConnectedError(),
        ),
        patch(
            "apps.market.services.fallback.alt_bars",
            return_value=[{"ts": "x", "close": 9}],
        ) as alt,
    ):
        assert fetch_ohlc_24h("SPY", timeframe="5m") == [{"ts": "x", "close": 9}]
    alt.assert_called_once()
    assert alt.call_args.kwargs["limit"] == 288  # _ALT_24H_LIMIT["5m"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_24h.py -k "fetch_ohlc_24h" -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_ohlc_24h'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/apps/market/services/ohlc.py`:

Add constants near `SESSION_TIMEFRAMES` (top of file, ~line 33):

```python
# Intraday timeframes for which the rolling 24h window is meaningful; daily keeps
# the fixed bar-count behavior.
INTRADAY_TIMEFRAMES = frozenset({"1m", "5m", "15m", "1h"})

# A 1m request keeps the current session at 1m and coarsens the older part of the
# 24h window to this (24h of 1m extended-hours bars is too many).
_COARSE_TIMEFRAME = "5m"

# Free-provider fallback is count-based and single-resolution; size ~24h per timeframe.
_ALT_24H_LIMIT = {"1m": 480, "5m": 288, "15m": 96, "1h": 48}
```

Add the fetch functions after `_union_window` (from Task 1):

```python
def fetch_ohlc_24h(ticker: str, *, timeframe: str) -> list[dict]:
    """Intraday OHLC over a rolling 24h window, never thinner than the current
    session (start = min(now-24h, session_open); end = now), extended hours
    included. A 1m request keeps the current session at 1m and coarsens the older
    portion of the window to 5m. Use this for snapshot capture; ``fetch_ohlc``
    (fixed count) stays the path for charts and tools.
    """
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    try:
        return cache.get_or_fetch(
            f"market:ohlc:{ticker}:{timeframe}:24h",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_24h_from_schwab(ticker, timeframe),
        )
    except SchwabNotConnectedError:
        from apps.market.services import fallback

        alt = fallback.alt_bars(ticker, timeframe, limit=_ALT_24H_LIMIT.get(timeframe, 288))
        if alt is None:
            raise
        return alt


def _fetch_window_from_schwab(
    ticker: str, timeframe: str, start_dt: datetime, end_dt: datetime
) -> list[dict]:
    """Fetch one resolution over [start_dt, end_dt] with extended hours, clamp rows
    to the window (Schwab honors it loosely), persist, and return rows."""
    client = get_schwab_client()
    method = getattr(client, _METHOD_BY_TIMEFRAME[timeframe])
    candles = schwab_json(
        method(
            ticker,
            start_datetime=start_dt,
            end_datetime=end_dt,
            need_extended_hours_data=True,
        )
    ).get("candles", [])
    rows = [
        r
        for r in _rows_from_candles(candles)
        if start_dt <= datetime.fromisoformat(r["ts"]) <= end_dt
    ]
    _persist_bars(ticker, timeframe, rows)
    return rows


def _fetch_24h_from_schwab(ticker: str, timeframe: str) -> list[dict]:
    window = _union_window(ticker)
    if window is None:
        return []
    start_dt, end_dt, session_open = window
    if timeframe != "1m" or session_open <= start_dt:
        # Non-1m, or no older portion (weekend / pre-market): single resolution.
        return _fetch_window_from_schwab(ticker, timeframe, start_dt, end_dt)
    # 1m request: coarsen the pre-session portion to 5m, keep the current session at 1m.
    older = [
        b
        for b in _fetch_window_from_schwab(ticker, _COARSE_TIMEFRAME, start_dt, session_open)
        if datetime.fromisoformat(b["ts"]) < session_open  # drop the boundary bar (belongs to 1m)
    ]
    recent = _fetch_window_from_schwab(ticker, "1m", session_open, end_dt)
    return older + recent
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_24h.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/ohlc.py backend/apps/market/tests/test_services_ohlc_24h.py
git commit -m "$(printf 'feat(market): add fetch_ohlc_24h rolling window with free-provider fallback\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Blended `1m`/`5m` resolution in `fetch_ohlc_24h`

**Files:**
- Modify: (verify only — blend logic already added in Task 2's `_fetch_24h_from_schwab`)
- Test: `backend/apps/market/tests/test_services_ohlc_24h.py`

**Interfaces:**
- Consumes: `fetch_ohlc_24h`, `_fetch_24h_from_schwab` (Task 2).

This task adds the tests that pin the blend contract (the implementation already exists from Task 2; if a test fails, fix `_fetch_24h_from_schwab`).

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/market/tests/test_services_ohlc_24h.py`:

```python
def _candle(dt: datetime, close: float) -> dict:
    return {"open": close, "high": close, "low": close, "close": close, "volume": 1,
            "datetime": int(dt.timestamp() * 1000)}


@pytest.mark.django_db
def test_fetch_ohlc_24h_blends_5m_older_and_1m_current_session():
    start = datetime(2026, 5, 27, 18, 0, tzinfo=UTC)
    end = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)
    session_open = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)

    def five_min(*_a, **_k):
        r = MagicMock()
        r.json.return_value = {"candles": [
            _candle(datetime(2026, 5, 28, 12, 0, tzinfo=UTC), 1),   # pre-session -> kept (5m)
            _candle(session_open, 9),                                # at open -> dropped from series
        ]}
        return r

    def one_min(*_a, **_k):
        r = MagicMock()
        r.json.return_value = {"candles": [
            _candle(datetime(2026, 5, 28, 14, 0, tzinfo=UTC), 2),   # in session -> kept (1m)
        ]}
        return r

    client = MagicMock()
    client.get_price_history_every_five_minutes.side_effect = five_min
    client.get_price_history_every_minute.side_effect = one_min
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="1m")

    assert [b["close"] for b in bars] == [1, 2]  # 5m pre-session, then 1m session; boundary dropped
    _, k5 = client.get_price_history_every_five_minutes.call_args
    assert (k5["start_datetime"], k5["end_datetime"]) == (start, session_open)
    _, k1 = client.get_price_history_every_minute.call_args
    assert (k1["start_datetime"], k1["end_datetime"]) == (session_open, end)


@pytest.mark.django_db
def test_fetch_ohlc_24h_1m_no_older_segment_when_window_starts_at_session_open():
    session_open = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)
    start = session_open  # weekend/pre-market: now-24h is after the session open
    end = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    resp = MagicMock()
    resp.json.return_value = {"candles": [_candle(datetime(2026, 5, 29, 14, 0, tzinfo=UTC), 2)]}
    client = MagicMock()
    client.get_price_history_every_minute.return_value = resp
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="1m")
    assert [b["close"] for b in bars] == [2]
    client.get_price_history_every_five_minutes.assert_not_called()
```

- [ ] **Step 2: Run test to verify it passes (implementation from Task 2)**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_24h.py -k "blend or no_older_segment" -v`
Expected: PASS. If FAIL, fix the blend logic in `_fetch_24h_from_schwab` (the `older` filter `< session_open` and the two window bounds) until green.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/market/tests/test_services_ohlc_24h.py
git commit -m "$(printf 'test(market): pin blended 1m/5m contract for fetch_ohlc_24h\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: Wire `_fetch_ohlc_section` to the 24h window

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (imports + `_fetch_ohlc_section`)
- Test: `backend/apps/snapshots/tests/test_ohlc_section_window.py` (create)
- Modify (test fixup): `backend/apps/snapshots/tests/test_capture_e2e_m5.py`
- Delete: `backend/apps/snapshots/tests/test_capture_overnight.py`

**Interfaces:**
- Consumes: `fetch_ohlc_24h` (Task 2), `INTRADAY_TIMEFRAMES` (Task 2), `fetch_ohlc` (existing).
- Produces: `_fetch_ohlc_section(...) -> {"data": {...}}` with `"window": "24h"` for intraday and `"coarse_timeframe": "5m"` for `1m`.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_ohlc_section_window.py`:

```python
from unittest.mock import patch

from apps.snapshots.services import _fetch_ohlc_section


def test_intraday_uses_24h_window():
    with patch(
        "apps.snapshots.services.fetch_ohlc_24h", return_value=[{"ts": "t", "close": 1}]
    ) as m:
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="5m")
    m.assert_called_once_with("SPY", timeframe="5m")
    assert out["data"]["window"] == "24h"
    assert out["data"]["timeframe"] == "5m"
    assert out["data"]["bars"] == [{"ts": "t", "close": 1}]
    assert "coarse_timeframe" not in out["data"]


def test_1m_marks_coarse_timeframe():
    with patch("apps.snapshots.services.fetch_ohlc_24h", return_value=[]):
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="1m")
    assert out["data"]["coarse_timeframe"] == "5m"


def test_daily_uses_fixed_bar_count():
    with patch(
        "apps.snapshots.services.fetch_ohlc", return_value=[{"ts": "t", "close": 1}]
    ) as m:
        out = _fetch_ohlc_section(watchlist_tickers=["SPY"], ohlc_timeframe="1d", ohlc_bars=60)
    m.assert_called_once_with("SPY", timeframe="1d", bars=60)
    assert "window" not in out["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_ohlc_section_window.py -v`
Expected: FAIL — `ImportError` for `fetch_ohlc_24h` (not yet imported in services) or assertion on `window`.

- [ ] **Step 3: Write minimal implementation**

In `backend/apps/snapshots/services/__init__.py`, change the OHLC import block (lines 20-25) from:

```python
from apps.market.services.ohlc import (
    SESSION_TIMEFRAMES,
    fetch_ohlc,
    fetch_ohlc_overnight,
    fetch_ohlc_session,
)
```

to:

```python
from apps.market.services.ohlc import (
    INTRADAY_TIMEFRAMES,
    fetch_ohlc,
    fetch_ohlc_24h,
)
```

Replace `_fetch_ohlc_section` (lines 102-129) with:

```python
def _fetch_ohlc_section(
    *,
    watchlist_tickers: list[str],
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
    **_,
) -> dict:
    ticker = _pick_ticker(ohlc_ticker, watchlist_tickers)
    if ohlc_timeframe in INTRADAY_TIMEFRAMES:
        # Always the rolling last-24h window; 1m blends the current session (1m)
        # with the older portion coarsened to 5m (see apps.market.services.ohlc).
        bars = fetch_ohlc_24h(ticker, timeframe=ohlc_timeframe)
        data = {"ticker": ticker, "timeframe": ohlc_timeframe, "bars": bars, "window": "24h"}
        if ohlc_timeframe == "1m":
            data["coarse_timeframe"] = "5m"
        return {"data": data}
    # Daily: keep the fixed bar count (a 24h window of daily bars is a single bar).
    bars = fetch_ohlc(ticker, timeframe=ohlc_timeframe, bars=ohlc_bars)
    return {"data": {"ticker": ticker, "timeframe": ohlc_timeframe, "bars": bars}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/snapshots/tests/test_ohlc_section_window.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Fix the e2e capture test mock target**

The capture e2e test mocks the old session fetcher. Find the references:

Run: `docker compose exec web grep -n "fetch_ohlc_session\|fetch_ohlc_overnight" apps/snapshots/tests/test_capture_e2e_m5.py`

Edit `backend/apps/snapshots/tests/test_capture_e2e_m5.py`: replace any `patch("apps.snapshots.services.fetch_ohlc_session", ...)` (and `fetch_ohlc_overnight`) with `patch("apps.snapshots.services.fetch_ohlc_24h", ...)`, and update any related call assertions to `fetch_ohlc_24h`. Keep return values/shape as-is (a list of bar dicts).

- [ ] **Step 6: Delete the overnight-capture test (mode is going away)**

```bash
git rm backend/apps/snapshots/tests/test_capture_overnight.py
```

- [ ] **Step 7: Run the snapshots capture tests**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_e2e_m5.py apps/snapshots/tests/test_ohlc_section_window.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tests/test_ohlc_section_window.py backend/apps/snapshots/tests/test_capture_e2e_m5.py
git commit -m "$(printf 'feat(snapshots): OHLC section always uses the rolling 24h window\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: News section always 24h; delete overnight news helper

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (`_fetch_news_section`, delete `_overnight_news_lookback_hours`)
- Test: `backend/apps/snapshots/tests/test_news_section_window.py` (create)
- Delete: `backend/apps/snapshots/tests/test_overnight_news_lookback.py`

**Interfaces:**
- Produces: `_fetch_news_section(*, watchlist_tickers, **_) -> {"data": {"items": [...]}}` (no `window` key).

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_news_section_window.py`:

```python
from unittest.mock import patch

from apps.snapshots.services import _fetch_news_section


def test_news_section_always_24h_default():
    with patch("apps.snapshots.services.fetch_news", return_value=[{"id": 1}]) as m:
        out = _fetch_news_section(watchlist_tickers=["SPY"])
    m.assert_called_once_with(["SPY"])
    assert out["data"] == {"items": [{"id": 1}]}
    assert "window" not in out["data"]


def test_overnight_news_helper_removed():
    import apps.snapshots.services as svc

    assert not hasattr(svc, "_overnight_news_lookback_hours")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_news_section_window.py -v`
Expected: FAIL — `test_overnight_news_helper_removed` fails (helper still present) and/or the window assertion.

- [ ] **Step 3: Write minimal implementation**

In `backend/apps/snapshots/services/__init__.py`:

Delete `_overnight_news_lookback_hours` (lines 68-72).

Replace `_fetch_news_section` (lines 132-139) with:

```python
def _fetch_news_section(*, watchlist_tickers: list[str], **_) -> dict:
    return {"data": {"items": fetch_news(list(watchlist_tickers))}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/snapshots/tests/test_news_section_window.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Delete the stale helper test**

```bash
git rm backend/apps/snapshots/tests/test_overnight_news_lookback.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tests/test_news_section_window.py
git commit -m "$(printf 'feat(snapshots): news section always uses the 24h default lookback\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: Serializer (markdown) headers — 24h labels

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (`_render_ohlc`, `_render_news`)
- Test: `backend/apps/snapshots/tests/test_serializer_24h.py` (create)
- Modify (remove stale tests): `backend/apps/snapshots/tests/test_serializer_overnight.py`

**Interfaces:**
- Consumes: OHLC payload with `window == "24h"` and optional `coarse_timeframe`; news payload with `items`.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_serializer_24h.py`:

```python
from apps.snapshots.serializer import _render_news, _render_ohlc

_BAR = {"ts": "2026-05-28T14:00:00+00:00", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}


def test_render_ohlc_24h_blended_header():
    md = _render_ohlc(
        {"ticker": "SPY", "timeframe": "1m", "window": "24h", "coarse_timeframe": "5m", "bars": [_BAR]}
    )
    assert "last 24h" in md
    assert "1m current session, 5m prior" in md


def test_render_ohlc_24h_single_resolution_header():
    md = _render_ohlc({"ticker": "SPY", "timeframe": "5m", "window": "24h", "bars": [_BAR]})
    assert "last 24h" in md
    assert "current session" not in md


def test_render_news_always_24h_label():
    md = _render_news({"items": []})
    assert "last 24h" in md.lower()
    assert "overnight" not in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_serializer_24h.py -v`
Expected: FAIL — header strings don't match (current code emits `overnight` branch / no 24h suffix).

- [ ] **Step 3: Write minimal implementation**

In `backend/apps/snapshots/serializer.py`, change the header block in `_render_ohlc` (lines 228-230) from:

```python
    header = f"## OHLC ({payload.get('ticker', '?')} @ {payload.get('timeframe', '?')})"
    if payload.get("window") == "overnight":
        header += " — overnight (extended hours)"
```

to:

```python
    header = f"## OHLC ({payload.get('ticker', '?')} @ {payload.get('timeframe', '?')})"
    if payload.get("window") == "24h":
        header += (
            " — last 24h (1m current session, 5m prior)"
            if payload.get("coarse_timeframe")
            else " — last 24h"
        )
```

In `_render_news`, replace the overnight label lines (337-339) from:

```python
    items = payload.get("items", []) if isinstance(payload, dict) else (payload or [])
    overnight = isinstance(payload, dict) and payload.get("window") == "overnight"
    title = "## News (overnight, since the prior close)" if overnight else "## News (last 24h)"
```

to:

```python
    items = payload.get("items", []) if isinstance(payload, dict) else (payload or [])
    title = "## News (last 24h)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/snapshots/tests/test_serializer_24h.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Remove the two stale overnight-header tests (keep the board + gap-column tests)**

In `backend/apps/snapshots/tests/test_serializer_overnight.py`, delete the functions `test_render_news_overnight_header` and `test_render_ohlc_overnight_header` (they assert the removed overnight labels). **Keep** `test_render_overnight_groups_present_only`, `test_render_overnight_empty`, `test_render_quotes_adds_gap_columns_when_present`, `test_render_quotes_no_gap_columns_by_default`. Remove any now-unused imports (e.g. `_render_news`, `_render_ohlc`) flagged by ruff.

- [ ] **Step 6: Run the serializer tests**

Run: `docker compose exec web pytest apps/snapshots/tests/test_serializer_overnight.py apps/snapshots/tests/test_serializer_24h.py apps/snapshots/tests/test_serializer_news.py apps/snapshots/tests/test_serializer_ohlc_gap.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_24h.py backend/apps/snapshots/tests/test_serializer_overnight.py
git commit -m "$(printf 'feat(snapshots): render 24h labels for OHLC and news sections\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: Remove the overnight flag from the capture pipeline

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (`capture`, `capture_for_existing`, `quotes` fetcher)
- Modify: `backend/apps/snapshots/tasks.py`
- Modify: `backend/apps/snapshots/views.py`
- Test: `backend/apps/snapshots/tests/test_capture_no_overnight.py` (create)

**Interfaces:**
- Produces: `capture(...)` and `capture_for_existing(...)` no longer accept `overnight`; `capture_task` no longer accepts `overnight`; the `quotes` fetcher calls `fetch_quotes(watchlist_tickers)` (default `gap_context=False`); `GET /api/snapshots/` no longer filters on `overnight`.
- Note: `Snapshot.overnight` model field and the DRF serializers still exist after this task (removed in Tasks 8/9); the field simply stays at its `False` default.

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_capture_no_overnight.py`:

```python
import inspect

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture_for_existing
from apps.snapshots.tasks import capture_task


def test_capture_for_existing_has_no_overnight_param():
    assert "overnight" not in inspect.signature(capture_for_existing).parameters


def test_capture_task_has_no_overnight_param():
    assert "overnight" not in inspect.signature(capture_task).parameters


@pytest.mark.django_db
def test_quotes_fetcher_uses_default_gap_context():
    from unittest.mock import patch

    profile = TradingProfile.objects.create(name="t", default_provider="openai")
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.create(profile=profile, includes=["quotes"], status="pending")
    with patch(
        "apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 1}}
    ) as m:
        capture_for_existing(snap, watchlist_tickers=["SPY"])
    assert m.call_args.kwargs.get("gap_context", False) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_no_overnight.py -v`
Expected: FAIL — `overnight` still present in signatures / `gap_context` toggled.

- [ ] **Step 3: Edit `services/__init__.py`**

Replace the `quotes` fetcher (lines 172-174) from:

```python
    "quotes": lambda *, watchlist_tickers, overnight=False, **_: {
        "data": fetch_quotes(watchlist_tickers, gap_context=overnight)
    },
```

to:

```python
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
```

In `capture_for_existing` (lines 221-293): remove the `overnight: bool = False` parameter; delete the overnight block (lines 231-239: the `if overnight ...` includes auto-add, the `snap.overnight` set, and the `as_of` computation); remove `as_of = None` if it becomes unused; in the fetcher call remove the `overnight=overnight,` and `as_of=as_of,` kwargs (lines 266-267). Result:

```python
def capture_for_existing(
    snap: Snapshot,
    *,
    watchlist_tickers: Iterable[str] = (),
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
) -> Snapshot:
    """Fill in sections for an already-created Snapshot. Broadcasts progress over WS."""
    _broadcast(snap.id, {"event": "pending", "snapshot_id": snap.id, "includes": snap.includes})
    ok_count = 0
    _primary: str | None = None

    for kind in snap.includes:
        fetcher = _FETCHERS.get(kind)
        section = SnapshotSection.objects.create(
            snapshot=snap, kind=kind, status="pending", payload={}
        )
        _broadcast(snap.id, {"event": "section_started", "kind": kind})

        if fetcher is None:
            section.status = "failed"
            section.error = f"No fetcher for '{kind}'"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})
            continue

        try:
            result = fetcher(  # type: ignore[operator]
                snapshot_id=snap.id,
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
            )
            section.payload = result["data"] or {}
            section.status = "done"
            section.save()
            stamp_payload_tokens(section)
            if kind == "quotes" and _primary is None:
                _primary = primary_ticker_from_quotes(section.payload)
            ok_count += 1
            _broadcast(snap.id, {"event": "section_done", "kind": kind})
        except Exception as exc:
            section.status = "failed"
            section.error = f"{type(exc).__name__}: {exc}"
            section.save()
            _broadcast(snap.id, {"event": "section_failed", "kind": kind, "error": section.error})

    attached_client_images = _attach_client_captures(snap)

    reps = _representative_tickers(snap, list(watchlist_tickers), ohlc_ticker)
    snap.market_state = _build_market_state(reps)
    snap.primary_ticker = derive_primary_ticker(snap) if _primary is None else _primary
    snap.status = "ready" if (ok_count > 0 or attached_client_images) else "failed"
    snap.save()
    _broadcast(snap.id, {"event": snap.status, "snapshot_id": snap.id})
    return snap
```

In `capture` (lines 296-326): remove the `overnight: bool = False` parameter, remove `overnight=overnight,` from `Snapshot.objects.create(...)`, and remove `overnight=overnight,` from the `capture_for_existing(...)` call.

Check the remaining imports: `market_state` is still used by `_build_market_state`; keep it. If `math` is now unused (it was only used by `_overnight_news_lookback_hours`, deleted in Task 5), remove the `import math` line — run `docker compose exec web ruff check apps/snapshots/services/__init__.py` and fix any unused-import (F401) findings.

- [ ] **Step 4: Edit `tasks.py`**

Remove `overnight: bool = False,` from `capture_task`'s signature (line 23) and remove `overnight=overnight,` from the `capture_for_existing(...)` call (line 46).

- [ ] **Step 5: Edit `views.py`**

Remove the listing filter (lines 64-65):

```python
        if p.get("overnight") in ("true", "1"):
            qs = qs.filter(overnight=True)
```

Remove `overnight=bool(data.get("overnight", False)),` from `Snapshot.objects.create(...)` (line 84) and from `capture_task.delay(...)` (line 99).

- [ ] **Step 6: Run tests**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_no_overnight.py apps/snapshots/tests/test_capture_e2e_m5.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tasks.py backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_capture_no_overnight.py
git commit -m "$(printf 'refactor(snapshots): remove overnight flag from the capture pipeline\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 8: Remove `overnight` from the API serializers + FE surface; regenerate types

**Files:**
- Modify: `backend/apps/snapshots/serializers.py`
- Regenerate: `backend/schema.yml`, `frontend/src/api/schema.d.ts`
- Modify: `frontend/src/api/snapshots.ts`, `frontend/src/pages/SnapshotComposerPage.tsx`, `frontend/src/pages/snapshots/SnapshotTable.tsx`
- Modify (tests): `backend/apps/snapshots/tests/test_overnight_model.py`, `frontend/src/__tests__/SnapshotComposerPage.test.tsx`, `frontend/src/__tests__/hooks/useCreateSnapshot.test.tsx`

**Interfaces:**
- Produces: `SnapshotSerializer` and `SnapshotListSerializer` no longer expose `overnight`; FE `CaptureFields`/create payload/list row no longer reference `overnight`.

- [ ] **Step 1: Remove the field from both serializers**

In `backend/apps/snapshots/serializers.py`, delete the `"overnight",` entry from `SnapshotListSerializer.Meta.fields` (line 40) and from `SnapshotSerializer.Meta.fields` (line 77).

- [ ] **Step 2: Remove the stale backend model/serializer test**

In `backend/apps/snapshots/tests/test_overnight_model.py`, delete `test_overnight_defaults_false_and_serializes` (it asserts the serializer field). Leave `test_overnight_section_kind_allowed` for now (Task 9 fixes it).

- [ ] **Step 3: Regenerate the OpenAPI schema**

Run: `make schema`
Then confirm `overnight` is gone from the snapshot schemas:
Run: `git diff backend/schema.yml | grep -n overnight`
Expected: only deletions (lines prefixed `-`).

- [ ] **Step 4: Regenerate the frontend types (gen:api landmine)**

`pnpm gen:api` reads `../backend/schema.yml`, which is not mounted in the frontend container. Copy the schema in and run the generator against it:

```bash
docker compose cp backend/schema.yml frontend:/tmp/schema.yml
docker compose exec -w /app frontend pnpm exec openapi-typescript /tmp/schema.yml -o src/api/schema.d.ts
```

Confirm: `git diff frontend/src/api/schema.d.ts | grep -n overnight` shows only deletions. (If the container path differs, run `docker compose exec frontend pwd` and adjust `-w`.)

- [ ] **Step 5: Remove `overnight` from the FE API module**

In `frontend/src/api/snapshots.ts`, delete the three `overnight` references: the field in the snapshot response interface (line 14), the optional field in the create-payload interface (line 30), and the field in the list-row interface (line 87).

- [ ] **Step 6: Remove the composer's overnight toggle**

In `frontend/src/pages/SnapshotComposerPage.tsx`:
- Delete `overnight: boolean;` from the `CaptureFields` interface (line ~54).
- Delete `overnight: fields.overnight,` from the `createSnap.mutateAsync({...})` payload (line ~83).
- Delete the entire `function OvernightField({ overnight, onChange }: {...}) { ... }` component (starts line ~179).
- Delete `const [overnight, setOvernight] = useState(false);` (line ~284).
- Remove `overnight,` from the `runCapture({ ... })` fields object (line ~339).
- Delete the `<OvernightField overnight={overnight} onChange={setOvernight} />` render (line ~387).

- [ ] **Step 7: Remove the overnight badge from the table**

In `frontend/src/pages/snapshots/SnapshotTable.tsx`, delete the `{row.overnight && (<...>overnight</...>)}` badge block (lines ~50-52).

- [ ] **Step 8: Update FE tests**

- In `frontend/src/__tests__/SnapshotComposerPage.test.tsx`, delete the test `it("sends overnight: true when the overnight toggle is on", ...)` (line ~386).
- In `frontend/src/__tests__/hooks/useCreateSnapshot.test.tsx`, delete the `overnight: false,` line from the fixture (line ~18).
- (`observer.test.ts` and `BriefingPage.tsx` only mention "overnight" in copy — leave them.)

- [ ] **Step 9: Run FE checks**

Run: `docker compose exec frontend pnpm exec tsc --noEmit`
Expected: no errors referencing `overnight`.
Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposerPage.test.tsx src/__tests__/hooks/useCreateSnapshot.test.tsx`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/apps/snapshots/serializers.py backend/schema.yml frontend/src/api/schema.d.ts frontend/src/api/snapshots.ts frontend/src/pages/SnapshotComposerPage.tsx frontend/src/pages/snapshots/SnapshotTable.tsx frontend/src/__tests__/SnapshotComposerPage.test.tsx frontend/src/__tests__/hooks/useCreateSnapshot.test.tsx backend/apps/snapshots/tests/test_overnight_model.py
git commit -m "$(printf 'refactor(snapshots): drop overnight from API serializers and FE surface\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 9: Drop the `Snapshot.overnight` model field + migration

**Files:**
- Modify: `backend/apps/snapshots/models.py`
- Create: `backend/apps/snapshots/migrations/0014_remove_snapshot_overnight.py`
- Modify (test): `backend/apps/snapshots/tests/test_overnight_model.py`

**Interfaces:**
- Produces: `Snapshot` has no `overnight` field; migration `0014` removes the column (reversible).

- [ ] **Step 1: Fix the remaining model test (drop the `overnight=True` kwarg)**

In `backend/apps/snapshots/tests/test_overnight_model.py`, edit `test_overnight_section_kind_allowed`: change `Snapshot.objects.create(profile=profile, includes=["overnight"], overnight=True)` to `Snapshot.objects.create(profile=profile, includes=["overnight"])`. (This test validates the `overnight` *board section kind*, not the flag.) If the file no longer imports `SnapshotSerializer`/`SnapshotListSerializer` after Task 8's deletion, remove those unused imports.

- [ ] **Step 2: Remove the model field**

In `backend/apps/snapshots/models.py`, delete the line:

```python
    overnight = models.BooleanField(default=False, db_index=True)
```

- [ ] **Step 3: Generate the migration**

Run: `make makemigrations`
Expected: creates `backend/apps/snapshots/migrations/0014_remove_snapshot_overnight.py` containing a `RemoveField`. Verify its content matches:

```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("snapshots", "0013_snapshot_candidate_positions"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="snapshot",
            name="overnight",
        ),
    ]
```

- [ ] **Step 4: Apply and verify the migration**

Run: `make migrate`
Expected: applies `snapshots.0014` cleanly.
Run: `make check-migrations`
Expected: no missing-migration error.

- [ ] **Step 5: Run the model test**

Run: `docker compose exec web pytest apps/snapshots/tests/test_overnight_model.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/apps/snapshots/models.py backend/apps/snapshots/migrations/0014_remove_snapshot_overnight.py backend/apps/snapshots/tests/test_overnight_model.py
git commit -m "$(printf 'refactor(snapshots): drop Snapshot.overnight field\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 10: Delete dead session/overnight OHLC functions + their tests

**Files:**
- Modify: `backend/apps/market/services/ohlc.py`
- Delete: `backend/apps/market/tests/test_services_ohlc_overnight.py`
- Modify: `backend/apps/market/tests/test_services_ohlc.py`

**Interfaces:**
- Produces: `ohlc.py` exports only `fetch_ohlc`, `fetch_ohlc_24h` (+ helpers); `fetch_ohlc_session`, `fetch_ohlc_overnight`, `_session_window`, `_overnight_window`, `_fetch_session_from_schwab`, `_fetch_overnight_from_schwab`, `SESSION_TIMEFRAMES` are gone.

- [ ] **Step 1: Confirm nothing still references the dead functions**

Run: `docker compose exec web grep -rn "fetch_ohlc_session\|fetch_ohlc_overnight\|_session_window\|_overnight_window\|_fetch_session_from_schwab\|_fetch_overnight_from_schwab\|SESSION_TIMEFRAMES" apps --include=*.py`
Expected: matches only in `apps/market/services/ohlc.py` (definitions) and the two test files handled below.

- [ ] **Step 2: Delete the dead functions**

In `backend/apps/market/services/ohlc.py`, delete: `fetch_ohlc_session` (lines 55-77), `fetch_ohlc_overnight` (80-103), `_overnight_window` (106-128), `_fetch_overnight_from_schwab` (131-152), `_session_window` (169-196), `_fetch_session_from_schwab` (199-222), and the `SESSION_TIMEFRAMES` constant (lines 31-33). Keep `fetch_ohlc`, `_fetch_from_schwab`, `_rows_from_candles`, `_persist_bars`, `_METHOD_BY_TIMEFRAME`, and the Task 1/2 additions.

- [ ] **Step 3: Delete the overnight market test; trim session tests**

```bash
git rm backend/apps/market/tests/test_services_ohlc_overnight.py
```

In `backend/apps/market/tests/test_services_ohlc.py`, delete any test functions that reference `fetch_ohlc_session`, `_session_window`, or `_fetch_session_from_schwab` (found in Step 1). Keep the tests for `fetch_ohlc` (fixed-count). Remove the now-unused imports of the deleted names.

- [ ] **Step 4: Run the market OHLC tests**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc.py apps/market/tests/test_services_ohlc_24h.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/ohlc.py backend/apps/market/tests/test_services_ohlc.py
git commit -m "$(printf 'refactor(market): remove dead session/overnight OHLC fetchers\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 11: Full gates + conventions check

**Files:** none (verification only)

- [ ] **Step 1: Confirm no schema drift**

Run: `make schema && git diff --exit-code backend/schema.yml`
Expected: exit 0 (no diff — schema already regenerated in Task 8).

- [ ] **Step 2: Backend lint + types + full test suite**

Run: `make check`
Expected: PASS. If `ruff`/`mypy`/import-linter/`deptry` flags an unused import or symbol left behind (e.g. `math`, `market_state`, removed names), fix it and re-run.

- [ ] **Step 3: Project conventions check**

Invoke the `conventions-check` skill (or dispatch the `conventions-reviewer` subagent) on the working changes. Confirm no silent-failure landmines were introduced (Celery task registration unaffected — no task renamed; section `"done"`/`"ready"` untouched; no direct provider instantiation; no `0.0.0.0` bind; synthetic-snapshot-message pattern untouched).

- [ ] **Step 4: Sanity-run capture end to end (optional, manual)**

With the dev stack up and a profile configured, create a snapshot via the UI or API and confirm the OHLC section payload carries `"window": "24h"` (and `"coarse_timeframe": "5m"` for a 1m capture), and the rendered markdown shows `## OHLC (... ) — last 24h ...` and `## News (last 24h)`.

- [ ] **Step 5: Final commit (if Step 2/3 required fixes)**

```bash
git add -A
git commit -m "$(printf 'chore(snapshots): satisfy lint/type gates for 24h window change\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage:**
- §2.1 OHLC + news target → Tasks 4, 5. ✓
- §2.2 rolling 24h never-empty (union window) → Tasks 1-2 (`_union_window`). ✓
- §2.3 intraday default, daily unchanged, overnight removed → Tasks 4, 7, 9, 10. ✓
- §2.4 blended 1m/5m → Tasks 2-3. ✓
- §2.5 news always 24h → Task 5. ✓
- §3.1 dual `_persist_bars` per resolution → Task 2 (`_fetch_window_from_schwab` persists each segment under its true timeframe). ✓
- §4.1 add `fetch_ohlc_24h`, delete dead funcs, free-provider fallback → Tasks 2, 10. ✓
- §4.2 `_fetch_ohlc_section`/`_fetch_news_section` → Tasks 4, 5. ✓
- §4.3 serializer labels → Task 6. ✓
- §4.4 remove flag (model/views/tasks/serializers/schema/FE) + pipeline couplings (gap_context, board auto-add, as_of) → Tasks 7, 8, 9. ✓
- §4.5 keep board section → Global Constraints note; no task touches it. ✓
- §5 payload shape (`window`, `coarse_timeframe`) → Task 4. ✓
- §8 testing (new/update/remove) → distributed; routing matches the spec. ✓

**Placeholder scan:** none — every code/edit step shows the actual code or a content-anchored edit with line refs.

**Type consistency:** `fetch_ohlc_24h(ticker, *, timeframe)` used identically in Tasks 2, 4, and the e2e mock. `_union_window` returns the 3-tuple `(start, end, session_open)` in Tasks 1, 2, 3. `_fetch_ohlc_section` payload keys (`window`, `coarse_timeframe`) match the serializer reads in Task 6 and the spec §5. `INTRADAY_TIMEFRAMES` defined in Task 2, consumed in Task 4. ✓
