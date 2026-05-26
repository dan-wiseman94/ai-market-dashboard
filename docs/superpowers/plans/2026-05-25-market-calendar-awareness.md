# Market-Calendar Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dashboard calendar-aware across all markets it touches — resolving each ticker to the correct exchange calendar (NYSE/SIFMA/CME/CFE/crypto/LSE/JPX), handling holidays and half-days everywhere market state matters (snapshots, analytics, observer, triggers, UI), and adding a half-day-safe "relative-to-close" schedule mode.

**Architecture:** A new `apps/market/calendar/` package owns a calendar registry, per-symbol resolution (heuristics + an explicit `CalendarOverride`), a session/state API, and trading-day arithmetic — all built on `pandas-market-calendars`. The legacy `apps/observer/services/market_hours.py` becomes a thin back-compat shim. Consumers (snapshots, analytics, observer gate, trigger gate, a new beat task, and five frontend surfaces) call the shared service. Built in 6 phases; each phase leaves `make check` green and is independently shippable.

**Tech Stack:** Django 5 + DRF, Celery + django-celery-beat, Postgres, `pandas-market-calendars`, React + TypeScript + Vite + TanStack Query, Vitest + Testing Library. Everything runs in Docker.

---

## Spec

This plan implements `docs/superpowers/specs/2026-05-25-market-calendar-awareness-design.md`. Read it first.

## Environment & Workflow Notes (read once)

- **Everything runs in Docker.** Run backend tests with `docker compose exec web pytest <path> -v` and frontend tests with `docker compose exec frontend pnpm exec vitest run <path>`. The stack must be up (`make dev`). Editor-level import errors are expected (deps live in containers).
- **This is a git worktree** at `.claude/worktrees/market-calendar-awareness` on branch `worktree-market-calendar-awareness` (based on `origin/main`). If you bring up Docker from here, the main checkout's stack may already bind `127.0.0.1` ports — stop it first (`make down` in the main checkout) or run the suite from the main checkout against this branch. Confirm with the user at execution start.
- **Migrations:** `docker compose exec web python manage.py makemigrations <app>` then `docker compose exec web python manage.py migrate`. Commit the generated migration file.
- **Pre-commit hook (lefthook)** runs `ruff`/`ty`/`eslint` on staged files only. If it fails with container-relative path errors (a known bug), retry with `LEFTHOOK=0 git commit ...`. Do **not** use `LEFTHOOK=0` to skip real lint failures.
- **`config/celery.py` lists task packages explicitly** — `apps.observer` is already listed, so new tasks in `apps/observer/tasks.py` register automatically. New beat *schedules* must be added to `app.conf.beat_schedule`.
- **Commit after every task.** Conventional messages (`feat(market):`, `feat(observer):`, `test(...)`, `fix(...)`). End each commit body with the Co-Authored-By trailer the harness uses.
- **`pandas-market-calendars` calendar identifiers:** NYSE is `"NYSE"`. The non-NYSE ids (`SIFMA_US`, `CFE`, `CME_Equity`, `LSE`, `JPX`, `"24/7"`) are pinned in Task 1. **Verify each against the installed version** with `docker compose exec web python -c "import pandas_market_calendars as mcal; print(mcal.get_calendar_names())"` before trusting session behavior for those markets. Session-behavior assertions in this plan's tests only cover NYSE (holidays/half-days) and crypto (24/7), which are unambiguous; other calendars are wired + resolution-tested but not session-asserted.

## File Structure

**New (backend):**
- `backend/apps/market/calendar/__init__.py` — public exports.
- `backend/apps/market/calendar/registry.py` — `MARKETS`, `MARKET_CHOICES`, `get_market_calendar`.
- `backend/apps/market/calendar/heuristics.py` — `classify(symbol) -> market_key`.
- `backend/apps/market/calendar/resolve.py` — `calendar_for(symbol)`, resolution cache.
- `backend/apps/market/calendar/sessions.py` — `market_state`, `is_open`, `any_market_open`, `add_trading_days`, `session_close_on`, `MarketState`.
- `backend/apps/market/serializers.py` — `CalendarOverrideSerializer`.
- `backend/apps/market/tests/test_calendar_*.py` — unit tests.

**Modified (backend):**
- `backend/apps/market/models.py` — add `CalendarOverride`.
- `backend/apps/market/views.py`, `urls.py` — calendar-status + override CRUD.
- `backend/apps/observer/services/market_hours.py` — shim.
- `backend/apps/observer/services/run.py` — per-watchlist gate.
- `backend/apps/observer/models.py`, `serializers.py`, `views.py`, `tasks.py` — relative-to-close.
- `backend/config/celery.py` — beat schedule.
- `backend/apps/triggers/dsl.py` — `tickers_in_condition`; `backend/apps/triggers/tasks.py` — per-trigger gate.
- `backend/apps/snapshots/models.py` — `market_state`; `services/__init__.py` — stamp; `serializer.py` — banner.
- `backend/apps/analytics/services/leaderboard.py` — trading-day forward returns.

**New / modified (frontend):**
- `frontend/src/api/market.ts` — calendar-status + override types/calls.
- `frontend/src/hooks/useMarketStatus.ts` (new), `frontend/src/components/MarketStatusBadge.tsx` (new), `frontend/src/components/SymbolCalendarOverridesCard.tsx` (new).
- `frontend/src/components/layout/TopNav.tsx`, `frontend/src/pages/Settings.tsx`, `frontend/src/pages/SnapshotComposerPage.tsx`, `frontend/src/pages/SchedulesPage.tsx`, `frontend/src/api/observer.ts`, `frontend/src/components/analytics/ProviderLeaderboardCard.tsx`, `frontend/src/hooks/useAnalytics.ts`.

---

## Phase 1 — Core calendar service

Goal: a self-contained `apps/market/calendar/` package + back-compat shim. No consumer behavior changes yet. App stays green.

### Task 1: Calendar registry

**Files:**
- Create: `backend/apps/market/calendar/__init__.py`
- Create: `backend/apps/market/calendar/registry.py`
- Test: `backend/apps/market/tests/test_calendar_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_registry.py
import pytest

from apps.market.calendar.registry import MARKETS, MARKET_CHOICES, get_market_calendar


def test_markets_has_the_seven_keys():
    assert set(MARKETS) == {
        "us_equity", "us_bond", "cme_futures", "cfe_futures", "crypto", "lse", "jpx"
    }


def test_market_choices_mirrors_markets():
    assert {k for k, _ in MARKET_CHOICES} == set(MARKETS)


@pytest.mark.parametrize("key", list(MARKETS))
def test_get_market_calendar_returns_cached_calendar(key):
    cal_a = get_market_calendar(key)
    cal_b = get_market_calendar(key)
    assert cal_a is cal_b  # cached at import / memoized


def test_unknown_key_falls_back_to_us_equity():
    assert get_market_calendar("nonsense") is get_market_calendar("us_equity")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.market.calendar`.

- [ ] **Step 3: Write the implementation**

```python
# backend/apps/market/calendar/__init__.py
"""Market-calendar service: registry, resolution, sessions, trading-day math."""
```

```python
# backend/apps/market/calendar/registry.py
"""Maps logical market keys to pandas-market-calendars identifiers, cached."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas_market_calendars as mcal

# market_key -> mcal calendar id. Verify ids against the installed version with
# `mcal.get_calendar_names()` before relying on non-NYSE session behavior.
MARKETS: dict[str, str] = {
    "us_equity": "NYSE",
    "us_bond": "SIFMA_US",
    "cme_futures": "CME_Equity",
    "cfe_futures": "CFE",
    "crypto": "24/7",
    "lse": "LSE",
    "jpx": "JPX",
}

MARKET_CHOICES: list[tuple[str, str]] = [
    ("us_equity", "US equities (NYSE/NASDAQ)"),
    ("us_bond", "US bonds (SIFMA)"),
    ("cme_futures", "CME futures"),
    ("cfe_futures", "CFE / VIX futures"),
    ("crypto", "Crypto (24/7)"),
    ("lse", "London (LSE)"),
    ("jpx", "Tokyo (JPX)"),
]

DEFAULT_MARKET = "us_equity"


@lru_cache(maxsize=None)
def get_market_calendar(market_key: str) -> Any:
    """Return the cached mcal calendar for a market key; unknown -> us_equity."""
    mcal_id = MARKETS.get(market_key) or MARKETS[DEFAULT_MARKET]
    return mcal.get_calendar(mcal_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_registry.py -v`
Expected: PASS (4 tests; the parametrized one expands to 7).

> If a non-NYSE id raises `RuntimeError: Cannot find calendar`, fix the id in `MARKETS` using `mcal.get_calendar_names()` and re-run.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/calendar/__init__.py backend/apps/market/calendar/registry.py backend/apps/market/tests/test_calendar_registry.py
git commit -m "feat(market): calendar registry with 7 market keys"
```

### Task 2: Symbol → market heuristics

**Files:**
- Create: `backend/apps/market/calendar/heuristics.py`
- Test: `backend/apps/market/tests/test_calendar_heuristics.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_heuristics.py
import pytest

from apps.market.calendar.heuristics import classify


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("SPY", "us_equity"),
        ("aapl", "us_equity"),        # case-insensitive
        ("$VIX", "us_equity"),        # cash index quoted on equity hours
        ("TLT", "us_equity"),         # bond ETF follows equities
        ("/ES", "cme_futures"),
        ("ES", "cme_futures"),
        ("/NQ", "cme_futures"),
        ("/VX", "cfe_futures"),
        ("VX", "cfe_futures"),        # VIX future, not the cash index
        ("BTC-USD", "crypto"),
        ("eth-usdt", "crypto"),
        ("VOD.L", "lse"),
        ("7203.T", "jpx"),
        ("", "us_equity"),            # empty -> default, never raises
    ],
)
def test_classify(symbol, expected):
    assert classify(symbol) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_heuristics.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# backend/apps/market/calendar/heuristics.py
"""Pattern rules that guess a market key from a bare ticker string.

Precedence inside calendar_for(): explicit override > classify() > default.
classify() itself is ordered: futures > crypto > international suffix > default.
"""

from __future__ import annotations

# Known CME future roots (index/commodity). Extend as needed.
_CME_ROOTS = {"ES", "NQ", "RTY", "YM", "CL", "GC", "SI", "ZB", "ZN", "ZF", "NG", "HG"}
_CFE_ROOTS = {"VX"}
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LTC", "BCH"}
_CRYPTO_QUOTE_SUFFIXES = ("-USD", "-USDT", "-USDC", "-EUR")


def classify(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return "us_equity"

    root = s[1:] if s.startswith("/") else s

    # Futures (leading slash or a known root)
    if s.startswith("/") or root in _CME_ROOTS or root in _CFE_ROOTS:
        if root in _CFE_ROOTS:
            return "cfe_futures"
        return "cme_futures"

    # Crypto (quote-currency suffix or a known base symbol)
    if any(s.endswith(suf) for suf in _CRYPTO_QUOTE_SUFFIXES):
        return "crypto"
    if s in _CRYPTO_BASES:
        return "crypto"

    # International equity suffixes
    if s.endswith(".L"):
        return "lse"
    if s.endswith(".T"):
        return "jpx"

    return "us_equity"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_heuristics.py -v`
Expected: PASS (15 cases).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/calendar/heuristics.py backend/apps/market/tests/test_calendar_heuristics.py
git commit -m "feat(market): symbol->market heuristic classifier"
```

### Task 3: Resolution (`calendar_for`) with cache

**Files:**
- Create: `backend/apps/market/calendar/resolve.py`
- Test: `backend/apps/market/tests/test_calendar_resolve.py`

> Phase-1 `calendar_for` = heuristic + default + an in-process cache. The explicit `CalendarOverride` lookup is added in Task 9 (Phase 2); the cache + `clear_resolution_cache()` hook are introduced here so Task 9 only has to wire invalidation.

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_resolve.py
from apps.market.calendar.resolve import calendar_for, clear_resolution_cache


def test_calendar_for_uses_heuristic():
    assert calendar_for("SPY") == "us_equity"
    assert calendar_for("BTC-USD") == "crypto"
    assert calendar_for("/ES") == "cme_futures"


def test_calendar_for_is_cached_and_clearable():
    clear_resolution_cache()
    assert calendar_for("SPY") == "us_equity"   # populates cache
    clear_resolution_cache()                     # must not raise
    assert calendar_for("SPY") == "us_equity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# backend/apps/market/calendar/resolve.py
"""Resolve a bare ticker to a market key: override -> heuristic -> default.

The CalendarOverride lookup is added in Phase 2; until then this is
heuristic + default. Results are cached per-process and invalidated by
CalendarOverride.save()/delete() (wired in Phase 2).
"""

from __future__ import annotations

import logging

from apps.market.calendar.heuristics import classify

log = logging.getLogger(__name__)

_cache: dict[str, str] = {}


def clear_resolution_cache() -> None:
    _cache.clear()


def calendar_for(symbol: str) -> str:
    """Return the market key for a symbol. Never raises."""
    key = (symbol or "").strip().upper()
    if not key:
        return "us_equity"
    if key in _cache:
        return _cache[key]
    market = classify(key)
    _cache[key] = market
    return market
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_resolve.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/calendar/resolve.py backend/apps/market/tests/test_calendar_resolve.py
git commit -m "feat(market): symbol resolution with clearable cache"
```

### Task 4: Session state + `is_open`

**Files:**
- Create: `backend/apps/market/calendar/sessions.py`
- Modify: `backend/apps/market/calendar/__init__.py`
- Test: `backend/apps/market/tests/test_calendar_sessions.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_sessions.py
from freezegun import freeze_time

from apps.market.calendar.sessions import MarketState, is_open, market_state


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET — NYSE open
def test_regular_session_open():
    st = market_state(market="us_equity")
    assert isinstance(st, MarketState)
    assert st.is_open is True
    assert st.phase == "open"
    assert st.is_early_close is False


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_weekend_closed():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "weekend"
    assert st.next_open is not None


@freeze_time("2026-05-25 14:00:00")  # Memorial Day (last Mon of May) — NYSE closed
def test_holiday_closed():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "holiday"


@freeze_time("2026-11-27 18:30:00")  # Fri after Thanksgiving, 13:30 ET — past 13:00 early close
def test_half_day_after_early_close():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.is_early_close is True


@freeze_time("2026-11-27 16:00:00")  # 11:00 ET — open on a half day
def test_half_day_open_before_early_close():
    st = market_state(market="us_equity")
    assert st.is_open is True
    assert st.is_early_close is True


@freeze_time("2026-04-18 14:00:00")  # Saturday — crypto still open
def test_crypto_always_open():
    assert is_open(symbol="BTC-USD") is True
    assert is_open(symbol="SPY") is False


@freeze_time("2026-04-15 14:00:00")
def test_to_json_is_iso_serializable():
    st = market_state(market="us_equity")
    d = st.to_json()
    assert d["is_open"] is True
    assert isinstance(d["session_close"], str)  # ISO string
    assert d["market_key"] == "us_equity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_sessions.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the implementation**

```python
# backend/apps/market/calendar/sessions.py
"""Session state + open/closed checks, holiday- and half-day-aware."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from apps.market.calendar.registry import get_market_calendar
from apps.market.calendar.resolve import calendar_for

log = logging.getLogger(__name__)

_LOOKAHEAD_DAYS = 16  # window for next_open / next_close search


@dataclass(frozen=True)
class MarketState:
    market_key: str
    phase: str  # open|closed|weekend|holiday|half_day|premarket|postmarket
    is_open: bool
    session_open: datetime | None
    session_close: datetime | None
    is_early_close: bool
    as_of: datetime | None      # most recent session close at/just before `at`
    next_open: datetime | None
    next_close: datetime | None

    def to_json(self) -> dict:
        def iso(v: datetime | None) -> str | None:
            return v.isoformat() if v else None

        return {
            "market_key": self.market_key,
            "phase": self.phase,
            "is_open": self.is_open,
            "session_open": iso(self.session_open),
            "session_close": iso(self.session_close),
            "is_early_close": self.is_early_close,
            "as_of": iso(self.as_of),
            "next_open": iso(self.next_open),
            "next_close": iso(self.next_close),
        }


def _resolve_market(symbol: str | None, market: str | None) -> str:
    if market:
        return market
    if symbol:
        return calendar_for(symbol)
    return "us_equity"


def market_state(
    *, symbol: str | None = None, market: str | None = None, at: datetime | None = None
) -> MarketState:
    now = at or timezone.now()
    market_key = _resolve_market(symbol, market)
    cal = get_market_calendar(market_key)

    # Plain schedule (no pre/post) over a window around `now`: robust across all
    # calendars incl. 24/7 crypto, and the window means the UTC date never
    # selects the wrong session.
    start = (now - timedelta(days=4)).date()
    end = (now + timedelta(days=_LOOKAHEAD_DAYS)).date()
    try:
        sched = cal.schedule(start_date=start, end_date=end)
    except Exception as exc:  # mcal can raise on odd ranges; treat as closed
        log.warning("market_state schedule failed for %s: %s", market_key, exc)
        return MarketState(market_key, "closed", False, None, None, False, None, None, None)

    today_open = today_close = None
    is_open_now = False
    is_early = False
    as_of = None
    next_open = next_close = None

    for _idx, row in sched.iterrows():
        o = row["market_open"].to_pydatetime()
        c = row["market_close"].to_pydatetime()
        if o.date() == now.date():
            today_open, today_close = o, c
            # A regular NYSE session is 6.5h; anything shorter is an early close.
            is_early = (c - o) < timedelta(hours=6, minutes=30)
        if o <= now <= c:
            is_open_now = True
        if c <= now and (as_of is None or c > as_of):
            as_of = c  # most recent session close at/before now
        if next_open is None and o > now:
            next_open = o
        if next_close is None and c > now:
            next_close = c

    if is_open_now:
        phase = "open"
    elif today_open is not None:
        phase = "half_day" if is_early else "closed"  # session exists today, now outside it
    else:
        phase = "weekend" if now.weekday() >= 5 else "holiday"

    return MarketState(
        market_key=market_key,
        phase=phase,
        is_open=is_open_now,
        session_open=today_open,
        session_close=today_close,
        is_early_close=is_early,
        as_of=as_of,
        next_open=next_open,
        next_close=next_close,
    )


def is_open(*, symbol: str | None = None, market: str | None = None, at: datetime | None = None) -> bool:
    return market_state(symbol=symbol, market=market, at=at).is_open
```

> Note: `is_early_close` uses a simple, robust heuristic — a session shorter than the regular 6.5h NYSE day is an early close. mcal's `schedule()` already reflects half-days in `market_close`, so no special-case table is needed. Phases are `open | closed | weekend | holiday | half_day`; pre/post-market labeling is deferred (not needed for the regular-session gate, and `start="pre"` raises on calendars like `24/7`).

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_sessions.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Wire the package exports**

```python
# backend/apps/market/calendar/__init__.py
"""Market-calendar service: registry, resolution, sessions, trading-day math."""

from apps.market.calendar.registry import MARKET_CHOICES, MARKETS, get_market_calendar
from apps.market.calendar.resolve import calendar_for, clear_resolution_cache
from apps.market.calendar.sessions import MarketState, is_open, market_state

__all__ = [
    "MARKETS",
    "MARKET_CHOICES",
    "get_market_calendar",
    "calendar_for",
    "clear_resolution_cache",
    "MarketState",
    "market_state",
    "is_open",
]
```

- [ ] **Step 6: Commit**

```bash
git add backend/apps/market/calendar/sessions.py backend/apps/market/calendar/__init__.py backend/apps/market/tests/test_calendar_sessions.py
git commit -m "feat(market): session state with holiday/half-day awareness"
```

### Task 5: Trading-day arithmetic

**Files:**
- Modify: `backend/apps/market/calendar/sessions.py`
- Modify: `backend/apps/market/calendar/__init__.py`
- Test: `backend/apps/market/tests/test_calendar_trading_days.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_trading_days.py
from datetime import UTC, datetime

from apps.market.calendar.sessions import add_trading_days, session_close_on


def test_add_trading_days_skips_weekend():
    # Fri 2026-04-17 + 1 trading day = Mon 2026-04-20
    fri = datetime(2026, 4, 17, 14, 0, tzinfo=UTC)
    nxt = add_trading_days("us_equity", fri, 1)
    assert nxt.date() == datetime(2026, 4, 20).date()


def test_add_trading_days_skips_holiday():
    # Fri 2026-05-22 + 1 trading day skips Memorial Day (Mon 5/25) -> Tue 5/26
    fri = datetime(2026, 5, 22, 14, 0, tzinfo=UTC)
    nxt = add_trading_days("us_equity", fri, 1)
    assert nxt.date() == datetime(2026, 5, 26).date()


def test_crypto_counts_every_day():
    sat = datetime(2026, 4, 18, 0, 0, tzinfo=UTC)
    nxt = add_trading_days("crypto", sat, 1)
    assert nxt.date() == datetime(2026, 4, 19).date()


def test_session_close_on_regular_day():
    close = session_close_on("us_equity", datetime(2026, 4, 15).date())
    assert close is not None
    assert close.hour == 20  # 16:00 ET (EDT) == 20:00 UTC


def test_session_close_on_half_day_is_early():
    close = session_close_on("us_equity", datetime(2026, 11, 27).date())
    assert close is not None
    assert close.hour == 18  # 13:00 ET (EST) == 18:00 UTC


def test_session_close_on_non_trading_day_is_none():
    assert session_close_on("us_equity", datetime(2026, 4, 18).date()) is None  # Saturday
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_trading_days.py -v`
Expected: FAIL — `ImportError: cannot import name 'add_trading_days'`.

- [ ] **Step 3: Append the implementation to `sessions.py`**

```python
# append to backend/apps/market/calendar/sessions.py
from datetime import date as _date


def add_trading_days(market: str, anchor: datetime, n: int) -> datetime:
    """Return `anchor` advanced by `n` trading sessions on `market`'s calendar.

    The returned datetime keeps `anchor`'s time-of-day but lands on the date of
    the n-th valid trading day at/after the next session. crypto counts daily.
    """
    cal = get_market_calendar(market)
    buffer_days = max(n * 3 + 10, 16)
    valid = cal.valid_days(
        start_date=anchor.date(), end_date=(anchor + timedelta(days=buffer_days)).date()
    )
    dates = [d.date() for d in valid]
    if not dates:
        return anchor + timedelta(days=n)
    # index of the first valid day >= anchor's date
    base = 0
    for i, d in enumerate(dates):
        if d >= anchor.date():
            base = i
            break
    target_idx = min(base + n, len(dates) - 1)
    target = dates[target_idx]
    return datetime(
        target.year, target.month, target.day, anchor.hour, anchor.minute, tzinfo=anchor.tzinfo
    )


def session_close_on(market: str, on_date: _date) -> datetime | None:
    """The actual close (half-day-aware) for `market` on `on_date`, or None."""
    cal = get_market_calendar(market)
    try:
        sched = cal.schedule(start_date=on_date, end_date=on_date)
    except Exception as exc:
        log.warning("session_close_on failed for %s %s: %s", market, on_date, exc)
        return None
    if sched.empty:
        return None
    return sched.iloc[0]["market_close"].to_pydatetime()
```

- [ ] **Step 4: Add to `__init__.py` exports**

Add `add_trading_days` and `session_close_on` to the imports from `sessions` and to `__all__` in `backend/apps/market/calendar/__init__.py`:

```python
from apps.market.calendar.sessions import (
    MarketState,
    add_trading_days,
    is_open,
    market_state,
    session_close_on,
)
```

(and add `"add_trading_days"`, `"session_close_on"` to `__all__`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_trading_days.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/market/calendar/sessions.py backend/apps/market/calendar/__init__.py backend/apps/market/tests/test_calendar_trading_days.py
git commit -m "feat(market): trading-day arithmetic (add_trading_days, session_close_on)"
```

### Task 6: `any_market_open` (union)

**Files:**
- Modify: `backend/apps/market/calendar/sessions.py`, `__init__.py`
- Test: `backend/apps/market/tests/test_calendar_any_open.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_any_open.py
from freezegun import freeze_time

from apps.market.calendar.sessions import any_market_open


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_any_open_true_when_crypto_present():
    assert any_market_open(["SPY", "BTC-USD"]) is True


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_any_open_false_when_all_equities():
    assert any_market_open(["SPY", "QQQ"]) is False


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET
def test_empty_defaults_to_us_equity_open():
    assert any_market_open([]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_any_open.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Append the implementation**

```python
# append to backend/apps/market/calendar/sessions.py
from collections.abc import Iterable


def any_market_open(symbols: Iterable[str], at: datetime | None = None) -> bool:
    """True if any symbol's market is open. Empty -> us_equity check."""
    syms = [s for s in symbols if s]
    if not syms:
        return is_open(market="us_equity", at=at)
    # Resolve to distinct markets first so we call market_state once per market.
    markets = {calendar_for(s) for s in syms}
    return any(is_open(market=m, at=at) for m in markets)
```

Add `any_market_open` to `__init__.py` imports + `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_any_open.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/calendar/sessions.py backend/apps/market/calendar/__init__.py backend/apps/market/tests/test_calendar_any_open.py
git commit -m "feat(market): any_market_open union helper"
```

### Task 7: Back-compat shim for `market_hours`

**Files:**
- Modify: `backend/apps/observer/services/market_hours.py`
- Test: existing `backend/apps/observer/tests/test_market_hours.py` must still pass.

- [ ] **Step 1: Replace the module body with a shim**

```python
# backend/apps/observer/services/market_hours.py
"""Back-compat shim. Canonical service is apps.market.calendar.

Existing callers import is_market_open / market_status (NYSE). New code should
import from apps.market.calendar instead.
"""

from __future__ import annotations

from datetime import datetime

from apps.market.calendar import is_open as _is_open
from apps.market.calendar import market_state as _market_state


def is_market_open(at: datetime | None = None) -> bool:
    return _is_open(market="us_equity", at=at)


def market_status(at: datetime | None = None) -> dict:
    st = _market_state(market="us_equity", at=at)
    return {
        "is_open": st.is_open,
        "next_open": st.next_open,
        "next_close": st.next_close,
    }
```

- [ ] **Step 2: Run the existing market-hours tests**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_market_hours.py -v`
Expected: PASS (all existing tests — `is_market_open` open/weekend/holiday, `market_status` open/off-hours).

> If `test_market_status_returns_open_during_session` checks `next_close.date()`, the shim's `next_close` is a tz-aware datetime as before — should pass unchanged.

- [ ] **Step 3: Run the whole calendar + observer suite to confirm no regressions**

Run: `docker compose exec web pytest backend/apps/market/tests/ backend/apps/observer/tests/ -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/observer/services/market_hours.py
git commit -m "refactor(observer): market_hours delegates to apps.market.calendar shim"
```

---

## Phase 2 — CalendarOverride model + API + Settings card

Goal: persist explicit per-symbol overrides, surface them via API + the Settings hub, and make `calendar_for` honor them.

### Task 8: `CalendarOverride` model + migration

**Files:**
- Modify: `backend/apps/market/models.py`
- Create: migration (generated)
- Test: `backend/apps/market/tests/test_calendar_override_model.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_override_model.py
import pytest
from django.db import IntegrityError

from apps.market.models import CalendarOverride


@pytest.mark.django_db
def test_symbol_is_uppercased_on_save():
    o = CalendarOverride.objects.create(symbol="btc-usd", market_key="crypto")
    assert o.symbol == "BTC-USD"


@pytest.mark.django_db
def test_symbol_is_unique():
    CalendarOverride.objects.create(symbol="SPY", market_key="us_equity")
    with pytest.raises(IntegrityError):
        CalendarOverride.objects.create(symbol="SPY", market_key="crypto")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_override_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'CalendarOverride'`.

- [ ] **Step 3: Add the model**

```python
# append to backend/apps/market/models.py
# at top of file, add:
from apps.market.calendar.registry import MARKET_CHOICES
```

```python
# append after NewsItem
class CalendarOverride(models.Model):
    """Explicit symbol -> market-key override; beats heuristics in calendar_for()."""

    symbol = models.CharField(max_length=16, unique=True)
    market_key = models.CharField(max_length=16, choices=MARKET_CHOICES)
    note = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.symbol} -> {self.market_key}"

    def save(self, *args, **kwargs) -> None:
        self.symbol = (self.symbol or "").strip().upper()
        super().save(*args, **kwargs)
        from apps.market.calendar.resolve import clear_resolution_cache

        clear_resolution_cache()

    def delete(self, *args, **kwargs):
        from apps.market.calendar.resolve import clear_resolution_cache

        result = super().delete(*args, **kwargs)
        clear_resolution_cache()
        return result
```

- [ ] **Step 4: Generate the migration + run the test**

```bash
docker compose exec web python manage.py makemigrations market
docker compose exec web pytest backend/apps/market/tests/test_calendar_override_model.py -v
```
Expected: migration created (e.g. `00NN_calendaroverride.py`); tests PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/models.py backend/apps/market/migrations/ backend/apps/market/tests/test_calendar_override_model.py
git commit -m "feat(market): CalendarOverride model"
```

### Task 9: Honor overrides in `calendar_for`

**Files:**
- Modify: `backend/apps/market/calendar/resolve.py`
- Test: `backend/apps/market/tests/test_calendar_override_resolve.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_override_resolve.py
import pytest

from apps.market.calendar.resolve import calendar_for, clear_resolution_cache
from apps.market.models import CalendarOverride


@pytest.mark.django_db
def test_override_beats_heuristic():
    clear_resolution_cache()
    assert calendar_for("SPY") == "us_equity"  # heuristic
    CalendarOverride.objects.create(symbol="SPY", market_key="crypto")  # save() clears cache
    assert calendar_for("SPY") == "crypto"


@pytest.mark.django_db
def test_deleting_override_reverts_to_heuristic():
    o = CalendarOverride.objects.create(symbol="FOO", market_key="crypto")
    assert calendar_for("FOO") == "crypto"
    o.delete()  # clears cache
    assert calendar_for("FOO") == "us_equity"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_override_resolve.py -v`
Expected: FAIL — both return the heuristic value (override ignored).

- [ ] **Step 3: Edit `resolve.py`**

Replace the `calendar_for` body and add `_override_for`:

```python
# backend/apps/market/calendar/resolve.py  (replace calendar_for, add helper)
def calendar_for(symbol: str) -> str:
    """Return the market key for a symbol: override -> heuristic -> default. Never raises."""
    key = (symbol or "").strip().upper()
    if not key:
        return "us_equity"
    if key in _cache:
        return _cache[key]
    market = _override_for(key) or classify(key)
    _cache[key] = market
    return market


def _override_for(symbol: str) -> str | None:
    # Lazy import: avoids AppRegistryNotReady at module load.
    from apps.market.models import CalendarOverride

    try:
        row = CalendarOverride.objects.filter(symbol=symbol).only("market_key").first()
    except Exception as exc:  # DB unavailable during some mgmt commands
        log.debug("override lookup skipped for %s: %s", symbol, exc)
        return None
    return row.market_key if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_override_resolve.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/calendar/resolve.py backend/apps/market/tests/test_calendar_override_resolve.py
git commit -m "feat(market): calendar_for honors CalendarOverride"
```

### Task 10: Override CRUD API + calendar-status endpoint

**Files:**
- Create: `backend/apps/market/serializers.py`
- Modify: `backend/apps/market/views.py`, `backend/apps/market/urls.py`
- Test: `backend/apps/market/tests/test_calendar_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/market/tests/test_calendar_api.py
import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_create_and_list_override():
    c = APIClient()
    r = c.post("/api/market/calendar-overrides/", {"symbol": "spy", "market_key": "crypto"}, format="json")
    assert r.status_code == 201
    assert r.json()["symbol"] == "SPY"
    r2 = c.get("/api/market/calendar-overrides/")
    assert any(row["symbol"] == "SPY" for row in r2.json())


@pytest.mark.django_db
def test_reject_unknown_market_key():
    c = APIClient()
    r = c.post("/api/market/calendar-overrides/", {"symbol": "X", "market_key": "mars"}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_calendar_status_for_symbol():
    c = APIClient()
    r = c.get("/api/market/calendar-status/?symbol=BTC-USD&symbol=SPY")
    assert r.status_code == 200
    markets = r.json()["markets"]
    assert markets["crypto"]["is_open"] is True
    assert markets["us_equity"]["is_open"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_api.py -v`
Expected: FAIL — 404 (routes not registered).

- [ ] **Step 3: Add serializer, views, urls**

```python
# backend/apps/market/serializers.py
from typing import ClassVar

from rest_framework import serializers

from apps.market.models import CalendarOverride


class CalendarOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarOverride
        fields: ClassVar = ["id", "symbol", "market_key", "note", "created_at", "updated_at"]
        read_only_fields: ClassVar = ["created_at", "updated_at"]
```

```python
# backend/apps/market/views.py  — add imports
from rest_framework import viewsets

from apps.market.calendar import MARKETS, calendar_for, market_state
from apps.market.models import CalendarOverride
from apps.market.serializers import CalendarOverrideSerializer
```

```python
# backend/apps/market/views.py  — add a ViewSet + a function view
class CalendarOverrideViewSet(viewsets.ModelViewSet):
    queryset = CalendarOverride.objects.all().order_by("symbol")
    serializer_class = CalendarOverrideSerializer


@require_GET
def calendar_status(request: HttpRequest) -> JsonResponse:
    symbols = request.GET.getlist("symbol")
    markets: set[str] = set(request.GET.getlist("market"))
    for s in symbols:
        markets.add(calendar_for(s))
    if not markets:
        markets.add("us_equity")
        markets.update(
            CalendarOverride.objects.values_list("market_key", flat=True).distinct()
        )
    out: dict[str, dict] = {}
    for m in sorted(markets):
        if m not in MARKETS:
            continue
        st = market_state(market=m)
        out[m] = {
            "is_open": st.is_open,
            "phase": st.phase,
            "is_early_close": st.is_early_close,
            "next_open": st.next_open.isoformat() if st.next_open else None,
            "next_close": st.next_close.isoformat() if st.next_close else None,
        }
    return JsonResponse({"markets": out})
```

```python
# backend/apps/market/urls.py  — full file
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "market"

router = DefaultRouter()
router.register("calendar-overrides", views.CalendarOverrideViewSet, basename="calendar-override")

urlpatterns = [
    path("quotes/", views.quotes, name="quotes"),
    path("ohlc/", views.ohlc, name="ohlc"),
    path("positions/", views.positions, name="positions"),
    path("context/", views.context, name="context"),
    path("chain/", views.chain, name="chain"),
    path("news/", views.news, name="news"),
    path("calendar-status/", views.calendar_status, name="calendar-status"),
    *router.urls,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/market/tests/test_calendar_api.py -v`
Expected: PASS (3).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/serializers.py backend/apps/market/views.py backend/apps/market/urls.py backend/apps/market/tests/test_calendar_api.py
git commit -m "feat(market): calendar-overrides CRUD + calendar-status endpoint"
```

### Task 11: Frontend API client for calendar

**Files:**
- Modify: `frontend/src/api/market.ts`

- [ ] **Step 1: Edit the import + append types/calls**

Change line 1 of `frontend/src/api/market.ts`:

```ts
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
```

Append:

```ts
export type MarketKey =
  | "us_equity" | "us_bond" | "cme_futures" | "cfe_futures" | "crypto" | "lse" | "jpx";

export interface CalendarOverride {
  id: number;
  symbol: string;
  market_key: MarketKey;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface CalendarMarketStatus {
  is_open: boolean;
  phase: string;
  is_early_close: boolean;
  next_open: string | null;
  next_close: string | null;
}

export const listCalendarOverrides = () =>
  apiGet<CalendarOverride[]>("/api/market/calendar-overrides/");
export const createCalendarOverride = (body: { symbol: string; market_key: MarketKey; note?: string }) =>
  apiPost<CalendarOverride>("/api/market/calendar-overrides/", body);
export const deleteCalendarOverride = (id: number) =>
  apiDelete(`/api/market/calendar-overrides/${id}/`);

export const getCalendarStatus = (symbols: string[] = []) => {
  const qs = symbols.map((s) => `symbol=${encodeURIComponent(s)}`).join("&");
  return apiGet<{ markets: Record<string, CalendarMarketStatus> }>(
    `/api/market/calendar-status/${qs ? `?${qs}` : ""}`,
  );
};
```

> `apiPatch` is imported for parity with other modules even if unused here; if `eslint` flags the unused import, drop `apiPatch` from the import list.

- [ ] **Step 2: Type-check**

Run: `docker compose exec frontend pnpm exec tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/market.ts
git commit -m "feat(frontend): calendar override + status API client"
```

### Task 12: Settings card — `SymbolCalendarOverridesCard`

**Files:**
- Create: `frontend/src/hooks/useCalendarOverrides.ts`
- Create: `frontend/src/components/SymbolCalendarOverridesCard.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Test: `frontend/src/__tests__/SymbolCalendarOverridesCard.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SymbolCalendarOverridesCard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SymbolCalendarOverridesCard from "@/components/SymbolCalendarOverridesCard";
import type { CalendarOverride } from "@/api/market";

const mockCreate = vi.fn();
const mockDelete = vi.fn();
const mockUseOverrides = vi.fn();

vi.mock("@/hooks/useCalendarOverrides", () => ({
  useCalendarOverrides: () => mockUseOverrides(),
  useCreateCalendarOverride: () => ({ mutate: mockCreate }),
  useDeleteCalendarOverride: () => ({ mutate: mockDelete }),
}));

const rows: CalendarOverride[] = [
  { id: 1, symbol: "BTC-USD", market_key: "crypto", note: "", created_at: "", updated_at: "" },
];

beforeEach(() => {
  mockUseOverrides.mockReturnValue({ data: rows });
  mockCreate.mockReset();
  mockDelete.mockReset();
});

describe("SymbolCalendarOverridesCard", () => {
  it("lists existing overrides", () => {
    render(<SymbolCalendarOverridesCard />);
    expect(screen.getByText("BTC-USD")).toBeInTheDocument();
    expect(screen.getByText(/crypto/i)).toBeInTheDocument();
  });

  it("submitting the add form calls create with the symbol + market", async () => {
    const user = userEvent.setup();
    render(<SymbolCalendarOverridesCard />);
    await user.type(screen.getByPlaceholderText(/symbol/i), "eth-usd");
    await user.selectOptions(screen.getByLabelText(/market/i), "crypto");
    await user.click(screen.getByRole("button", { name: /add/i }));
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ symbol: "eth-usd", market_key: "crypto" });
  });

  it("clicking delete calls delete with the id", async () => {
    const user = userEvent.setup();
    render(<SymbolCalendarOverridesCard />);
    await user.click(screen.getByRole("button", { name: /delete BTC-USD/i }));
    expect(mockDelete).toHaveBeenCalledWith(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SymbolCalendarOverridesCard.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the hook**

```ts
// frontend/src/hooks/useCalendarOverrides.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listCalendarOverrides,
  createCalendarOverride,
  deleteCalendarOverride,
} from "@/api/market";

const KEY = ["calendar-overrides"];

export function useCalendarOverrides() {
  return useQuery({ queryKey: KEY, queryFn: listCalendarOverrides });
}

export function useCreateCalendarOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createCalendarOverride,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteCalendarOverride() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteCalendarOverride,
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
```

- [ ] **Step 4: Write the component**

```tsx
// frontend/src/components/SymbolCalendarOverridesCard.tsx
import { useState } from "react";
import {
  useCalendarOverrides,
  useCreateCalendarOverride,
  useDeleteCalendarOverride,
} from "@/hooks/useCalendarOverrides";
import type { MarketKey } from "@/api/market";

const MARKETS: Array<[MarketKey, string]> = [
  ["us_equity", "US equities (NYSE/NASDAQ)"],
  ["us_bond", "US bonds (SIFMA)"],
  ["cme_futures", "CME futures"],
  ["cfe_futures", "CFE / VIX futures"],
  ["crypto", "Crypto (24/7)"],
  ["lse", "London (LSE)"],
  ["jpx", "Tokyo (JPX)"],
];

export default function SymbolCalendarOverridesCard() {
  const { data: overrides } = useCalendarOverrides();
  const create = useCreateCalendarOverride();
  const del = useDeleteCalendarOverride();
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<MarketKey>("us_equity");

  return (
    <div className="p-4 rounded border border-slate-800 space-y-4">
      <div>
        <h2 className="text-lg font-medium">Symbol calendars</h2>
        <p className="text-xs text-slate-500">
          Override which market calendar a symbol uses. Unlisted symbols are auto-classified
          (NYSE by default).
        </p>
      </div>

      <ul className="space-y-1 text-sm">
        {(overrides ?? []).map((o) => (
          <li key={o.id} className="flex items-center justify-between border-t border-slate-800 pt-1">
            <span className="font-mono">{o.symbol}</span>
            <span className="text-slate-400">{o.market_key}</span>
            <button
              type="button"
              aria-label={`delete ${o.symbol}`}
              onClick={() => del.mutate(o.id)}
              className="px-2 py-0.5 text-xs rounded bg-red-900 hover:bg-red-800"
            >
              Delete
            </button>
          </li>
        ))}
      </ul>

      <form
        className="flex items-end gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (!symbol.trim()) return;
          create.mutate(
            { symbol: symbol.trim(), market_key: market },
            { onSuccess: () => setSymbol("") },
          );
        }}
      >
        <input
          placeholder="Symbol (e.g. BTC-USD)"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
        />
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-500">Market</span>
          <select
            aria-label="market"
            value={market}
            onChange={(e) => setMarket(e.target.value as MarketKey)}
            className="px-2 py-1 rounded bg-slate-900 border border-slate-700"
          >
            {MARKETS.map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </label>
        <button type="submit" className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">
          Add
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Mount it in Settings**

```tsx
// frontend/src/pages/Settings.tsx
import ProviderConfigCard from "@/components/ProviderConfigCard";
import SchwabConnectionCard from "@/components/SchwabConnectionCard";
import SymbolCalendarOverridesCard from "@/components/SymbolCalendarOverridesCard";

export default function Settings() {
  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <SchwabConnectionCard />
      <ProviderConfigCard />
      <SymbolCalendarOverridesCard />
    </main>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SymbolCalendarOverridesCard.test.tsx`
Expected: PASS (3).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useCalendarOverrides.ts frontend/src/components/SymbolCalendarOverridesCard.tsx frontend/src/pages/Settings.tsx frontend/src/__tests__/SymbolCalendarOverridesCard.test.tsx
git commit -m "feat(frontend): symbol calendar overrides card in Settings"
```

---

## Phase 3 — Backend wiring (snapshots, analytics, gates)

Goal: every backend surface consumes the calendar service. App stays green.

### Task 13: `Snapshot.market_state` field + migration

**Files:**
- Modify: `backend/apps/snapshots/models.py`
- Create: migration

- [ ] **Step 1: Add the field**

In `backend/apps/snapshots/models.py`, add to `Snapshot` after `captured_at`:

```python
    market_state = models.JSONField(null=True, blank=True)
```

- [ ] **Step 2: Generate migration**

Run: `docker compose exec web python manage.py makemigrations snapshots`
Expected: `00NN_snapshot_market_state.py` created.

- [ ] **Step 3: Verify migration applies**

Run: `docker compose exec web python manage.py migrate`
Expected: applies cleanly.

- [ ] **Step 4: Commit**

```bash
git add backend/apps/snapshots/models.py backend/apps/snapshots/migrations/
git commit -m "feat(snapshots): add Snapshot.market_state JSON field"
```

### Task 14: Stamp `market_state` at capture

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py`
- Test: `backend/apps/snapshots/tests/test_capture_market_state.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/snapshots/tests/test_capture_market_state.py
import pytest
from freezegun import freeze_time

from apps.profiles.models import TradingProfile
from apps.snapshots.services import _build_market_state, capture_for_existing
from apps.snapshots.models import Snapshot


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_build_market_state_union():
    st = _build_market_state(["BTC-USD", "SPY"])
    assert st["any_open"] is True               # crypto open
    assert st["markets"]["crypto"]["is_open"] is True
    assert st["markets"]["us_equity"]["is_open"] is False
    assert "BTC-USD" in st["representative_tickers"]


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")
def test_capture_stamps_market_state():
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(profile=profile, includes=[], status="pending")
    capture_for_existing(snap, watchlist_tickers=["BTC-USD"])
    snap.refresh_from_db()
    assert snap.market_state is not None
    assert "crypto" in snap.market_state["markets"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/snapshots/tests/test_capture_market_state.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_market_state'`.

- [ ] **Step 3: Implement the helpers + stamp in `capture_for_existing`**

Add near the top of `backend/apps/snapshots/services/__init__.py` (after existing imports):

```python
from django.utils import timezone

from apps.market.calendar import any_market_open, calendar_for, market_state
```

Add the helpers (module level):

```python
def _representative_tickers(snap, watchlist_tickers, ohlc_ticker) -> list[str]:
    quotes = snap.sections.filter(kind="quotes", status="done").first()
    if quotes and isinstance(quotes.payload, dict) and quotes.payload:
        return list(quotes.payload.keys())
    if watchlist_tickers:
        return list(watchlist_tickers)
    if ohlc_ticker:
        return [ohlc_ticker]
    return []


def _build_market_state(tickers: list[str]) -> dict:
    markets = {calendar_for(t) for t in tickers} or {"us_equity"}
    states = {m: market_state(market=m).to_json() for m in sorted(markets)}
    return {
        "captured_at": timezone.now().isoformat(),
        "any_open": any_market_open(tickers),
        "markets": states,
        "representative_tickers": list(tickers),
    }
```

In `capture_for_existing`, immediately before `snap.status = "ready" if ok_count > 0 else "failed"`:

```python
    reps = _representative_tickers(snap, list(watchlist_tickers), ohlc_ticker)
    snap.market_state = _build_market_state(reps)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/snapshots/tests/test_capture_market_state.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tests/test_capture_market_state.py
git commit -m "feat(snapshots): stamp market_state at capture"
```

### Task 15: Market-state banner in `serialize_for_ai`

**Files:**
- Modify: `backend/apps/snapshots/serializer.py`
- Test: `backend/apps/snapshots/tests/test_serializer_market_banner.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/snapshots/tests/test_serializer_market_banner.py
import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.serializer import serialize_for_ai


@pytest.mark.django_db
def test_banner_present_when_market_closed():
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(
        profile=profile,
        includes=[],
        status="ready",
        market_state={"any_open": False, "markets": {"us_equity": {"is_open": False}}},
    )
    out = serialize_for_ai(snap, provider="claude", model="")
    assert "Market state" in out
    assert "us_equity" in out


@pytest.mark.django_db
def test_no_banner_when_open():
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(
        profile=profile,
        includes=[],
        status="ready",
        market_state={"any_open": True, "markets": {"us_equity": {"is_open": True}}},
    )
    out = serialize_for_ai(snap, provider="claude", model="")
    assert "Market state" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_market_banner.py -v`
Expected: FAIL — first test fails (no banner).

- [ ] **Step 3: Add the banner**

In `serialize_for_ai`, after the `notes` block (after the `if snapshot.notes.strip():` append) and before `rendered: dict[str, str] = {}`:

```python
    ms = snapshot.market_state
    if ms and not ms.get("any_open", True):
        closed = [m for m, s in ms.get("markets", {}).items() if not s.get("is_open")]
        if closed:
            parts.append(
                f"> **Market state:** {', '.join(closed)} closed at capture — "
                f"data is as-of the last session close."
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_market_banner.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_market_banner.py
git commit -m "feat(snapshots): as-of market-state banner in AI payload"
```

### Task 16: Trading-day forward returns (analytics)

**Files:**
- Modify: `backend/apps/analytics/services/leaderboard.py`
- Test: `backend/apps/analytics/tests/test_leaderboard_trading_day.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/analytics/tests/test_leaderboard_trading_day.py
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.analytics.services.leaderboard import _forward_return_pct
from apps.market.models import OHLCBar


def _bar(ticker, ts, close):
    OHLCBar.objects.create(
        ticker=ticker, timeframe="1h", open=close, high=close, low=close,
        close=Decimal(str(close)), volume=1, ts=ts,
    )


@pytest.mark.django_db
def test_forward_return_uses_next_trading_session():
    # capture Wed 2026-04-15 20:00 UTC (close); +1 session = Thu 2026-04-16 close
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    _bar("SPY", at, 100.0)
    _bar("SPY", datetime(2026, 4, 16, 20, 0, tzinfo=UTC), 110.0)
    ret = _forward_return_pct("SPY", at, 24)
    assert ret == pytest.approx(10.0)


@pytest.mark.django_db
def test_forward_return_none_when_no_target_bar():
    at = datetime(2026, 4, 15, 20, 0, tzinfo=UTC)
    _bar("SPY", at, 100.0)  # only the t0 bar; no bar near the target session
    assert _forward_return_pct("SPY", at, 24) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/analytics/tests/test_leaderboard_trading_day.py -v`
Expected: FAIL — `test_forward_return_none_when_no_target_bar` fails (old code stale-fills with the t0 bar) and/or value mismatch.

- [ ] **Step 3: Rewrite the two helpers**

Replace `_forward_return_pct` and `_nearest_bar_close` in `backend/apps/analytics/services/leaderboard.py`. Add the calendar import near the top:

```python
from apps.market.calendar import add_trading_days, calendar_for, session_close_on
```

```python
def _forward_return_pct(ticker: str, at: datetime, forward_hours: int) -> float | None:
    """% change of `ticker` from capture to +N trading sessions on its calendar.

    forward_hours is reinterpreted as trading sessions (24h -> 1 session). Returns
    None (coverage gap) when a real bar is missing near either endpoint — never a
    stale fill.
    """
    market = calendar_for(ticker)
    sessions = max(1, round(forward_hours / 24))
    target_day = add_trading_days(market, at, sessions)
    target_close = session_close_on(market, target_day.date()) or target_day
    # 12h tolerance = half a daily session: finds the target session's bar
    # without bleeding back into the capture-day bar (which keeps coverage gaps honest).
    t0 = _nearest_bar_close(ticker, at, tolerance_hours=12)
    t1 = _nearest_bar_close(ticker, target_close, tolerance_hours=12)
    if t0 is None or t1 is None or t0 == 0:
        return None
    return (t1 - t0) / t0 * 100.0


def _nearest_bar_close(ticker: str, at: datetime, *, tolerance_hours: float) -> float | None:
    """Most recent bar at/just before `at`, but only within `tolerance_hours`."""
    lo = at - timedelta(hours=tolerance_hours)
    bar = (
        OHLCBar.objects.filter(ticker=ticker, ts__lte=at, ts__gte=lo)
        .only("close")
        .order_by("-ts")
        .first()
    )
    if bar is None:
        return None
    return float(bar.close)
```

(`timedelta` is already imported at the top of the file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/analytics/tests/test_leaderboard_trading_day.py -v`
Expected: PASS (2).

- [ ] **Step 5: Run the existing leaderboard tests for regressions**

Run: `docker compose exec web pytest backend/apps/analytics/ -q`
Expected: PASS. (If a prior test asserted the old wall-clock stale-fill behavior, update it to the trading-day semantics — note the change in the commit.)

- [ ] **Step 6: Commit**

```bash
git add backend/apps/analytics/services/leaderboard.py backend/apps/analytics/tests/test_leaderboard_trading_day.py
git commit -m "feat(analytics): trading-day forward returns with honest coverage gaps"
```

### Task 17: Observer gate resolves from watchlist

**Files:**
- Modify: `backend/apps/observer/services/run.py`
- Test: `backend/apps/observer/tests/test_run_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/observer/tests/test_run_gate.py
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import run_observer
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_skips_when_all_watched_markets_closed():
    profile = TradingProfile.objects.create(name="p", style="s")
    sched = ObserverSchedule.objects.create(
        name="eq", profile=profile, market_hours_only=True,
        default_watchlist_tickers=["SPY"],
    )
    with patch("apps.observer.services.run.capture") as cap:
        assert run_observer(sched.id) is None
        cap.assert_not_called()


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday — crypto open
def test_proceeds_when_a_watched_market_open():
    profile = TradingProfile.objects.create(name="p", style="s")
    sched = ObserverSchedule.objects.create(
        name="cx", profile=profile, market_hours_only=True,
        default_watchlist_tickers=["BTC-USD"], default_includes=[],
    )
    from apps.snapshots.models import Snapshot
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    with (
        patch("apps.observer.services.run.capture", return_value=snap) as cap,
        patch("apps.observer.services.run.run_ai_on_message"),
    ):
        run_observer(sched.id)
        cap.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_run_gate.py -v`
Expected: FAIL — current code uses NYSE `is_market_open()`, so the crypto schedule is skipped on Saturday (`cap.assert_called_once()` fails).

- [ ] **Step 3: Edit `run.py`**

Change the import on line 14:

```python
from apps.market.calendar import any_market_open
```

Replace the gate (currently lines ~39–41):

```python
    if sched.market_hours_only and not any_market_open(sched.default_watchlist_tickers):
        log.info("observer %s skipped: all watched markets closed", schedule_id)
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_run_gate.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/observer/services/run.py backend/apps/observer/tests/test_run_gate.py
git commit -m "feat(observer): gate fires on watchlist calendars (any-open)"
```

### Task 18: `tickers_in_condition` (trigger DSL)

**Files:**
- Modify: `backend/apps/triggers/dsl.py`
- Test: `backend/apps/triggers/tests/test_tickers_in_condition.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/triggers/tests/test_tickers_in_condition.py
from apps.triggers.dsl import tickers_in_condition


def test_collects_nested_tickers():
    cond = {
        "all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 1},
            {"any": [
                {"metric": "price", "ticker": "BTC-USD", "op": ">", "value": 1},
                {"not": {"metric": "pct_change", "ticker": "QQQ", "op": ">", "value": 1, "window": "1d"}},
            ]},
            {"metric": "vix", "op": ">", "value": 20},  # no ticker
        ]
    }
    assert tickers_in_condition(cond) == {"SPY", "BTC-USD", "QQQ"}


def test_empty_for_tickerless():
    assert tickers_in_condition({"metric": "vix", "op": ">", "value": 1}) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/triggers/tests/test_tickers_in_condition.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Add the function to `dsl.py`**

```python
# append to backend/apps/triggers/dsl.py
def tickers_in_condition(node: Any) -> set[str]:
    """Collect all leaf `ticker` values from a (validated or raw) condition tree."""
    out: set[str] = set()
    if not isinstance(node, dict):
        return out
    for key in ("all", "any"):
        if key in node and isinstance(node[key], list):
            for child in node[key]:
                out |= tickers_in_condition(child)
            return out
    if "not" in node:
        return tickers_in_condition(node["not"])
    ticker = node.get("ticker")
    if isinstance(ticker, str) and ticker:
        out.add(ticker)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/triggers/tests/test_tickers_in_condition.py -v`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/triggers/dsl.py backend/apps/triggers/tests/test_tickers_in_condition.py
git commit -m "feat(triggers): tickers_in_condition DSL walker"
```

### Task 19: Per-trigger market gate

**Files:**
- Modify: `backend/apps/triggers/tasks.py`
- Test: `backend/apps/triggers/tests/test_evaluate_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/triggers/tests/test_evaluate_gate.py
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger
from apps.triggers.tasks import evaluate_triggers


def _trigger(profile, name, ticker):
    return EventTrigger.objects.create(
        profile=profile, name=name,
        condition={"metric": "price", "ticker": ticker, "op": ">", "value": 1},
    )


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_all_equity_triggers_skipped_off_hours():
    profile = TradingProfile.objects.create(name="p", style="s")
    _trigger(profile, "eq", "SPY")
    result = evaluate_triggers()
    assert result.get("skipped") == "all_markets_closed"


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday — crypto open
def test_crypto_trigger_is_evaluated_off_hours():
    profile = TradingProfile.objects.create(name="p", style="s")
    _trigger(profile, "eq", "SPY")
    crypto = _trigger(profile, "cx", "BTC-USD")
    with (
        patch("apps.triggers.tasks.metrics.build_snapshot", return_value={}) as bs,
        patch("apps.triggers.tasks.cooldown_blocks", return_value=False),
        patch("apps.triggers.tasks.evaluator.evaluate", return_value=(False, {})),
        patch("apps.triggers.tasks.mark_rearmed"),
    ):
        evaluate_triggers()
        passed = list(bs.call_args[0][0])
        assert passed == [crypto]  # equity trigger filtered out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/triggers/tests/test_evaluate_gate.py -v`
Expected: FAIL — current global gate returns `skipped="market_closed"` (not `all_markets_closed`) and builds the snapshot over all triggers.

- [ ] **Step 3: Edit `evaluate_triggers`**

Change the import on line 14:

```python
from apps.market.calendar import any_market_open
```

Add near the other `apps.triggers` imports:

```python
from apps.triggers.dsl import tickers_in_condition
```

Remove the global gate (currently lines ~39–41):

```python
    if not is_market_open():
        logger.debug("trigger.tick.market_closed")
        return {"evaluated": 0, "fires": 0, "skipped": "market_closed"}
```

Replace the trigger fetch + snapshot build (currently ~lines 44–50) so it filters to live markets:

```python
    triggers = list(
        EventTrigger.objects.filter(enabled=True).select_related("profile"),
    )
    if not triggers:
        return {"evaluated": 0, "fires": 0}

    live = [t for t in triggers if any_market_open(tickers_in_condition(t.condition))]
    if not live:
        logger.debug("trigger.tick.all_markets_closed")
        return {"evaluated": 0, "fires": 0, "skipped": "all_markets_closed"}

    snapshot = metrics.build_snapshot(live)
```

Change the loop header `for trigger in triggers:` to `for trigger in live:`, and update the final summary's `triggers_evaluated=len(triggers)` / return `"evaluated": len(triggers)` to `len(live)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/triggers/tests/test_evaluate_gate.py -v`
Expected: PASS (2).

- [ ] **Step 5: Run the trigger suite for regressions**

Run: `docker compose exec web pytest backend/apps/triggers/ -q`
Expected: PASS. (Update any existing test that asserted `skipped="market_closed"`.)

- [ ] **Step 6: Commit**

```bash
git add backend/apps/triggers/tasks.py backend/apps/triggers/tests/test_evaluate_gate.py
git commit -m "feat(triggers): per-trigger market gate (resolve from condition tickers)"
```

---

## Phase 4 — Relative-to-close schedule mode

Goal: an opt-in schedule mode that fires `close_offset_minutes` before the day's *actual* close (half-day-safe), driven by a beat poller instead of a fixed cron.

### Task 20: `ObserverSchedule.fire_mode` + `close_offset_minutes`

**Files:**
- Modify: `backend/apps/observer/models.py`
- Create: migration

- [ ] **Step 1: Add the fields**

In `backend/apps/observer/models.py`, add to `ObserverSchedule`. First a choices list inside the class (near `MODE_CHOICES`):

```python
    FIRE_MODE_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("cron", "Cron"),
        ("relative_to_close", "Relative to close"),
    ]
```

Then add the fields (after `use_batch`):

```python
    fire_mode = models.CharField(max_length=20, choices=FIRE_MODE_CHOICES, default="cron")
    close_offset_minutes = models.PositiveIntegerField(
        default=5, help_text="Minutes before the actual session close to fire (relative_to_close)."
    )
```

- [ ] **Step 2: Generate migration + apply**

```bash
docker compose exec web python manage.py makemigrations observer
docker compose exec web python manage.py migrate
```
Expected: `00NN_observerschedule_fire_mode_...py` created and applied.

- [ ] **Step 3: Commit**

```bash
git add backend/apps/observer/models.py backend/apps/observer/migrations/
git commit -m "feat(observer): fire_mode + close_offset_minutes fields"
```

### Task 21: Serializer + viewset accept relative mode (cron optional)

**Files:**
- Modify: `backend/apps/observer/serializers.py`, `backend/apps/observer/views.py`
- Test: `backend/apps/observer/tests/test_relative_schedule_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/observer/tests/test_relative_schedule_api.py
import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_create_relative_schedule_without_cron():
    profile = TradingProfile.objects.create(name="p", style="s")
    c = APIClient()
    r = c.post("/api/observer/schedules/", {
        "name": "eod", "profile": profile.id,
        "fire_mode": "relative_to_close", "close_offset_minutes": 5,
    }, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["fire_mode"] == "relative_to_close"
    # no PeriodicTask for relative mode
    from apps.observer.models import ObserverSchedule
    assert ObserverSchedule.objects.get(id=r.json()["id"]).periodic_task is None


@pytest.mark.django_db
def test_cron_schedule_still_requires_cron():
    profile = TradingProfile.objects.create(name="p", style="s")
    c = APIClient()
    r = c.post("/api/observer/schedules/", {
        "name": "x", "profile": profile.id, "fire_mode": "cron",
    }, format="json")
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_relative_schedule_api.py -v`
Expected: FAIL — `cron` is currently required (first test 400s) / field unknown.

- [ ] **Step 3: Edit the serializer**

In `backend/apps/observer/serializers.py`:
- make `cron` optional: `cron = serializers.CharField(write_only=True, required=False)`
- add `"fire_mode"`, `"close_offset_minutes"` to the `fields` list.
- add a `validate`:

```python
    def validate(self, attrs):
        fire_mode = attrs.get("fire_mode") or (self.instance.fire_mode if self.instance else "cron")
        has_existing_pt = bool(self.instance and self.instance.periodic_task)
        if fire_mode == "cron" and not attrs.get("cron") and not has_existing_pt:
            raise serializers.ValidationError({"cron": "cron is required for cron fire_mode"})
        return attrs
```

- [ ] **Step 4: Edit the viewset**

In `backend/apps/observer/views.py`, update `perform_create` / `perform_update` so the PeriodicTask is only synced for `cron` mode:

```python
    def perform_create(self, serializer):
        cron = serializer.validated_data.pop("cron", None)
        instance = serializer.save()
        if instance.fire_mode == "cron" and cron:
            sync_periodic_task(instance, cron=cron)

    def perform_update(self, serializer):
        cron = serializer.validated_data.pop("cron", None)
        instance = serializer.save()
        if instance.fire_mode != "cron":
            # switched to / staying relative: drop any PeriodicTask
            if instance.periodic_task:
                delete_periodic_task(instance)
            return
        if cron is not None or "enabled" in serializer.validated_data:
            existing_cron = cron
            if existing_cron is None and instance.periodic_task and instance.periodic_task.crontab:
                c = instance.periodic_task.crontab
                existing_cron = (
                    f"{c.minute} {c.hour} {c.day_of_month} {c.month_of_year} {c.day_of_week}"
                )
            if existing_cron is None:
                existing_cron = "0 * * * *"
            sync_periodic_task(instance, cron=existing_cron)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_relative_schedule_api.py -v`
Expected: PASS (2).

- [ ] **Step 6: Run the observer serializer/sync suite for regressions**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_sync.py backend/apps/observer/tests/test_schedule_model.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/observer/serializers.py backend/apps/observer/views.py backend/apps/observer/tests/test_relative_schedule_api.py
git commit -m "feat(observer): API accepts relative_to_close schedules (cron optional)"
```

### Task 22: Beat poller `fire_close_relative_schedules`

**Files:**
- Create: `backend/apps/observer/services/close_relative.py`
- Modify: `backend/apps/observer/tasks.py`, `backend/config/celery.py`
- Test: `backend/apps/observer/tests/test_close_relative.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/apps/observer/tests/test_close_relative.py
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from apps.observer.models import ObserverSchedule
from apps.observer.services.close_relative import fire_due_close_relative
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
@freeze_time("2026-11-27 17:55:30")  # 5m before the 13:00 ET (18:00 UTC) half-day close
def test_fires_in_window_then_guards_same_day():
    profile = TradingProfile.objects.create(name="p", style="s")
    sched = ObserverSchedule.objects.create(
        name="eod", profile=profile, fire_mode="relative_to_close",
        close_offset_minutes=5, default_watchlist_tickers=["SPY"],
    )
    with patch("apps.observer.tasks.run_observer_task.delay") as delay:
        out = fire_due_close_relative()
        assert out["fired"] == 1
        delay.assert_called_once_with(schedule_id=sched.id)
        # second tick same minute -> guarded
        out2 = fire_due_close_relative()
        assert out2["fired"] == 0


@pytest.mark.django_db
@freeze_time("2026-11-27 15:00:00")  # well before the early close window
def test_does_not_fire_outside_window():
    profile = TradingProfile.objects.create(name="p", style="s")
    ObserverSchedule.objects.create(
        name="eod", profile=profile, fire_mode="relative_to_close",
        close_offset_minutes=5, default_watchlist_tickers=["SPY"],
    )
    with patch("apps.observer.tasks.run_observer_task.delay") as delay:
        assert fire_due_close_relative()["fired"] == 0
        delay.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_close_relative.py -v`
Expected: FAIL — `ModuleNotFoundError: apps.observer.services.close_relative`.

- [ ] **Step 3: Write the service**

```python
# backend/apps/observer/services/close_relative.py
"""Beat-driven firing for relative_to_close schedules (half-day-safe)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from apps.market.calendar import calendar_for, session_close_on
from apps.observer.models import ObserverSchedule

log = logging.getLogger(__name__)


def fire_due_close_relative(now: datetime | None = None) -> dict:
    now = now or timezone.now()
    fired = 0
    scheds = ObserverSchedule.objects.filter(enabled=True, fire_mode="relative_to_close")
    for s in scheds:
        symbols = s.default_watchlist_tickers or ["SPY"]
        market = calendar_for(symbols[0])
        close = session_close_on(market, now.date())
        if close is None:
            continue  # not a trading day for this market
        fire_at = close - timedelta(minutes=s.close_offset_minutes)
        if not (fire_at <= now < fire_at + timedelta(minutes=1)):
            continue
        if s.last_fired_at and s.last_fired_at.date() == now.date():
            continue  # once-per-day guard (closes the double-fire race)
        s.last_fired_at = now
        s.save(update_fields=["last_fired_at"])
        from apps.observer.tasks import run_observer_task

        run_observer_task.delay(schedule_id=s.id)
        fired += 1
    return {"fired": fired}
```

- [ ] **Step 4: Register the beat task**

Append to `backend/apps/observer/tasks.py`:

```python
@shared_task(name="observer.fire_close_relative_schedules")
def fire_close_relative_schedules() -> dict:
    from apps.observer.services.close_relative import fire_due_close_relative

    return fire_due_close_relative()
```

Add to `app.conf.beat_schedule` in `backend/config/celery.py`:

```python
    "fire-close-relative-schedules": {
        "task": "observer.fire_close_relative_schedules",
        "schedule": crontab(minute="*"),
    },
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec web pytest backend/apps/observer/tests/test_close_relative.py -v`
Expected: PASS (2). (This also proves the half-day self-adjustment: the fire window is computed from the 13:00 ET early close, not 16:00.)

- [ ] **Step 6: Commit**

```bash
git add backend/apps/observer/services/close_relative.py backend/apps/observer/tasks.py backend/config/celery.py backend/apps/observer/tests/test_close_relative.py
git commit -m "feat(observer): relative-to-close beat poller (half-day safe)"
```

### Task 23: Schedule form — fire_mode + offset controls

**Files:**
- Modify: `frontend/src/api/observer.ts`, `frontend/src/pages/SchedulesPage.tsx`
- Test: `frontend/src/__tests__/SchedulesPage.fireMode.test.tsx`

- [ ] **Step 1: Extend the API types**

In `frontend/src/api/observer.ts`:
- add `export type ObserverFireMode = "cron" | "relative_to_close";`
- add to `ObserverSchedule`: `fire_mode: ObserverFireMode;` and `close_offset_minutes: number;`
- in `CreateScheduleBody`, change `cron: string;` to `cron?: string;` and add `fire_mode?: ObserverFireMode;` and `close_offset_minutes?: number;`

- [ ] **Step 2: Write the failing test**

```tsx
// frontend/src/__tests__/SchedulesPage.fireMode.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SchedulesPage from "@/pages/SchedulesPage";

const mockCreate = vi.fn(() => Promise.resolve());

vi.mock("@/hooks/useSchedules", () => ({
  useSchedules: () => ({ data: [], isLoading: false }),
  useToggleSchedule: () => ({ mutate: vi.fn() }),
  useDeleteSchedule: () => ({ mutate: vi.fn() }),
  useRunSchedule: () => ({ mutate: vi.fn() }),
  useCreateSchedule: () => ({ mutateAsync: mockCreate, isPending: false }),
}));
vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: () => ({ data: [{ id: 1, name: "P1" }] }),
}));

beforeEach(() => mockCreate.mockClear());

describe("SchedulesPage relative-to-close", () => {
  it("shows the close-offset input only when fire_mode is relative_to_close", async () => {
    const user = userEvent.setup();
    render(<SchedulesPage />);
    await user.click(screen.getByRole("button", { name: /new schedule/i }));
    expect(screen.queryByLabelText(/minutes before close/i)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText(/fire mode/i), "relative_to_close");
    expect(screen.getByLabelText(/minutes before close/i)).toBeInTheDocument();
  });

  it("submits fire_mode + close_offset_minutes", async () => {
    const user = userEvent.setup();
    render(<SchedulesPage />);
    await user.click(screen.getByRole("button", { name: /new schedule/i }));
    await user.type(screen.getByLabelText(/^name$/i), "eod");
    await user.selectOptions(screen.getByLabelText(/fire mode/i), "relative_to_close");
    await user.click(screen.getByRole("button", { name: /^create$/i }));
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate.mock.calls[0][0]).toMatchObject({
      fire_mode: "relative_to_close",
      close_offset_minutes: 5,
    });
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SchedulesPage.fireMode.test.tsx`
Expected: FAIL — no fire-mode control.

- [ ] **Step 4: Edit `SchedulesPage.tsx`**

Add state (near the other `useState` calls):

```tsx
  const [fireMode, setFireMode] = useState<import("@/api/observer").ObserverFireMode>("cron");
  const [closeOffset, setCloseOffset] = useState(5);
```

Give the Name input an explicit id/label association if missing (the test queries `/^name$/i`); it already has `htmlFor="sched-name"` + label "Name" — good.

Add a fire-mode block inside the form (e.g. just before the cron block):

```tsx
          <div>
            <label className="block text-xs text-slate-500 mb-1" htmlFor="sched-fire-mode">Fire mode</label>
            <select
              id="sched-fire-mode"
              value={fireMode}
              onChange={(e) => setFireMode(e.target.value as import("@/api/observer").ObserverFireMode)}
              className="w-full px-2 py-1.5 rounded bg-slate-950 border border-slate-700"
            >
              <option value="cron">Cron schedule</option>
              <option value="relative_to_close">Relative to market close</option>
            </select>
            {fireMode === "relative_to_close" && (
              <label className="block text-xs text-slate-500 mt-2" htmlFor="sched-close-offset">
                Minutes before close
                <input
                  id="sched-close-offset"
                  type="number"
                  min={0}
                  value={closeOffset}
                  onChange={(e) => setCloseOffset(parseInt(e.target.value, 10) || 0)}
                  className="w-full px-2 py-1.5 rounded bg-slate-950 border border-slate-700 mt-1"
                />
              </label>
            )}
          </div>
```

Wrap the cron block so it only shows for cron mode: `{fireMode === "cron" && ( <existing cron block> )}`.

Update `onCreate` to send the new fields and omit cron for relative mode:

```tsx
    await create.mutateAsync({
      name, profile: profileId, enabled, market_hours_only: marketHoursOnly,
      objective_template: objective, mode, structured, use_batch: useBatch,
      fire_mode: fireMode,
      ...(fireMode === "cron" ? { cron } : { close_offset_minutes: closeOffset }),
    });
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SchedulesPage.fireMode.test.tsx`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/observer.ts frontend/src/pages/SchedulesPage.tsx frontend/src/__tests__/SchedulesPage.fireMode.test.tsx
git commit -m "feat(frontend): schedule fire-mode + close-offset controls"
```

---

## Phase 5 — Frontend status surfaces

Goal: surface market state in the UI (TopNav badge, snapshot composer banner) and clarify the leaderboard's trading-day semantics. (The `calendar-status` endpoint + API client already exist from Tasks 10–11.)

### Task 24: `useMarketStatus` hook + TopNav badge

**Files:**
- Create: `frontend/src/hooks/useMarketStatus.ts`, `frontend/src/components/MarketStatusBadge.tsx`
- Modify: `frontend/src/components/layout/TopNav.tsx`
- Test: `frontend/src/__tests__/MarketStatusBadge.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/MarketStatusBadge.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import MarketStatusBadge from "@/components/MarketStatusBadge";

const mockUse = vi.fn();
vi.mock("@/hooks/useMarketStatus", () => ({ useMarketStatus: () => mockUse() }));

beforeEach(() => mockUse.mockReset());

describe("MarketStatusBadge", () => {
  it("shows Open when the single market is open", () => {
    mockUse.mockReturnValue({ data: { markets: { us_equity: { is_open: true, phase: "open" } } } });
    render(<MarketStatusBadge />);
    expect(screen.getByTestId("market-status")).toHaveTextContent("Open");
  });

  it("shows Closed when the single market is closed", () => {
    mockUse.mockReturnValue({ data: { markets: { us_equity: { is_open: false, phase: "weekend" } } } });
    render(<MarketStatusBadge />);
    expect(screen.getByTestId("market-status")).toHaveTextContent("Closed");
  });

  it("summarizes N/M when multiple markets present", () => {
    mockUse.mockReturnValue({
      data: { markets: { us_equity: { is_open: false }, crypto: { is_open: true } } },
    });
    render(<MarketStatusBadge />);
    expect(screen.getByTestId("market-status")).toHaveTextContent("1/2 open");
  });

  it("renders nothing while loading (no data)", () => {
    mockUse.mockReturnValue({ data: undefined });
    const { container } = render(<MarketStatusBadge />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/MarketStatusBadge.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the hook**

```ts
// frontend/src/hooks/useMarketStatus.ts
import { useQuery } from "@tanstack/react-query";

import { getCalendarStatus } from "@/api/market";

export function useMarketStatus(symbols: string[] = []) {
  return useQuery({
    queryKey: ["market-status", [...symbols].sort()],
    queryFn: () => getCalendarStatus(symbols),
    refetchInterval: 60_000,
  });
}
```

- [ ] **Step 4: Write the badge**

```tsx
// frontend/src/components/MarketStatusBadge.tsx
import { useMarketStatus } from "@/hooks/useMarketStatus";

export default function MarketStatusBadge() {
  const { data } = useMarketStatus();
  const markets = data?.markets ?? {};
  const keys = Object.keys(markets);
  if (keys.length === 0) return null;

  const openCount = keys.filter((k) => markets[k].is_open).length;
  const anyOpen = openCount > 0;
  const label =
    keys.length === 1 ? (markets[keys[0]].is_open ? "Open" : "Closed") : `${openCount}/${keys.length} open`;
  const tip = keys.map((k) => `${k}: ${markets[k].is_open ? "open" : "closed"}`).join(", ");

  return (
    <span data-testid="market-status" title={tip} className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`h-2 w-2 rounded-full ${anyOpen ? "bg-emerald-400" : "bg-slate-500"}`} />
      <span>{label}</span>
    </span>
  );
}
```

- [ ] **Step 5: Mount in TopNav**

In `frontend/src/components/layout/TopNav.tsx`, import it and place it before `ConnectionStatusDot` inside the right-hand cluster:

```tsx
import MarketStatusBadge from "@/components/MarketStatusBadge";
```

```tsx
        <div className="flex items-center gap-4 text-[12px] text-ink-400 font-mono">
          <span className="hidden md:inline-flex items-center gap-1.5">
            <MarketStatusBadge />
          </span>
          <span className="hidden md:inline-flex items-center gap-1.5">
            <ConnectionStatusDot />
          </span>
          <NotificationBell />
        </div>
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/MarketStatusBadge.test.tsx`
Expected: PASS (4).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useMarketStatus.ts frontend/src/components/MarketStatusBadge.tsx frontend/src/components/layout/TopNav.tsx frontend/src/__tests__/MarketStatusBadge.test.tsx
git commit -m "feat(frontend): multi-calendar market status badge in TopNav"
```

### Task 25: Snapshot composer "market closed" banner

**Files:**
- Modify: `frontend/src/pages/SnapshotComposerPage.tsx`
- Test: `frontend/src/__tests__/SnapshotComposer.banner.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SnapshotComposer.banner.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SnapshotComposerPage from "@/pages/SnapshotComposerPage";

const mockMarketStatus = vi.fn();

vi.mock("@/hooks/useMarketStatus", () => ({ useMarketStatus: () => mockMarketStatus() }));
vi.mock("@/hooks/useProfiles", () => ({ useProfiles: () => ({ data: [{ id: 1, name: "P", default_includes: [] }] }) }));
vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: () => ({ data: [{ id: 1, name: "W", symbols: [{ ticker: "SPY" }] }] }),
}));
vi.mock("@/hooks/useCreateSnapshot", () => ({ useCreateSnapshot: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock("@/hooks/useCreateConsultThread", () => ({ useCreateConsultThread: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@/components/SnapshotSectionPicker", () => ({ default: () => <div /> }));

beforeEach(() => mockMarketStatus.mockReset());

describe("SnapshotComposer market banner", () => {
  it("shows the closed banner when a relevant market is closed", () => {
    mockMarketStatus.mockReturnValue({ data: { markets: { us_equity: { is_open: false } } } });
    render(<SnapshotComposerPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/market closed/i);
  });

  it("no banner when markets are open", () => {
    mockMarketStatus.mockReturnValue({ data: { markets: { us_equity: { is_open: true } } } });
    render(<SnapshotComposerPage />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposer.banner.test.tsx`
Expected: FAIL — no banner.

- [ ] **Step 3: Edit `SnapshotComposerPage.tsx`**

Add the import:

```tsx
import { useMarketStatus } from "@/hooks/useMarketStatus";
```

After the `tickers` `useMemo`, add:

```tsx
  const { data: marketStatus } = useMarketStatus(tickers);
  const closedMarkets = marketStatus
    ? Object.entries(marketStatus.markets).filter(([, s]) => !s.is_open).map(([k]) => k)
    : [];
```

Inside the returned `<main>`, right after the `<h1>`:

```tsx
      {closedMarkets.length > 0 && (
        <div role="status" className="rounded border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
          Market closed ({closedMarkets.join(", ")}) — this snapshot will be captured and labeled
          as-of the last session close.
        </div>
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposer.banner.test.tsx`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SnapshotComposerPage.tsx frontend/src/__tests__/SnapshotComposer.banner.test.tsx
git commit -m "feat(frontend): market-closed banner on snapshot composer"
```

### Task 26: Leaderboard trading-day label

**Files:**
- Modify: `frontend/src/components/analytics/ProviderLeaderboardCard.tsx`
- Test: `frontend/src/__tests__/ProviderLeaderboardCard.label.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/ProviderLeaderboardCard.label.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ProviderLeaderboardCard } from "@/components/analytics/ProviderLeaderboardCard";

vi.mock("@/hooks/useAnalytics", () => ({
  useLeaderboard: () => ({ data: { rows: [] }, isLoading: false, isError: false, error: null }),
}));

describe("ProviderLeaderboardCard", () => {
  it("explains the trading-day horizon + coverage", () => {
    render(<ProviderLeaderboardCard />);
    expect(screen.getByText(/trading session/i)).toBeInTheDocument();
    expect(screen.getByText(/coverage/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ProviderLeaderboardCard.label.test.tsx`
Expected: FAIL — no such text.

- [ ] **Step 3: Add a footnote**

In `frontend/src/components/analytics/ProviderLeaderboardCard.tsx`, add a footnote after the `</table>` (still inside the `AnalyticsCard` render function — wrap the table + footnote in a fragment):

```tsx
      {(data) => (
        <>
          <table className="w-full text-sm font-mono">
            {/* …unchanged… */}
          </table>
          <p className="mt-2 text-[11px] text-slate-500">
            Fwd % = return over 1 trading session on each ticker's calendar. Cov = coverage:
            share of runs with a real price bar at both endpoints (gaps shown as —).
          </p>
        </>
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/ProviderLeaderboardCard.label.test.tsx`
Expected: PASS (1).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/analytics/ProviderLeaderboardCard.tsx frontend/src/__tests__/ProviderLeaderboardCard.label.test.tsx
git commit -m "feat(frontend): clarify leaderboard trading-day horizon + coverage"
```

---

## Final verification (run after each phase, and at the end)

- [ ] **Backend:** `make lint` then `docker compose exec web pytest backend/apps/market backend/apps/observer backend/apps/triggers backend/apps/snapshots backend/apps/analytics -q` — all green.
- [ ] **Frontend:** `docker compose exec frontend pnpm run lint` and `docker compose exec frontend pnpm exec vitest run` — all green.
- [ ] **Full CI gate:** `make check`.
- [ ] **Manual smoke (optional):** with the stack up, `curl 'http://127.0.0.1:8000/api/market/calendar-status/?symbol=BTC-USD&symbol=SPY'` returns both markets; open `/settings` and add an override; open `/snapshot` on a weekend and confirm the banner.

## Acceptance criteria (maps to spec §1)

1. Calendars beyond NYSE exist + resolve (Tasks 1–3, 8–9). ✅ when `calendar_for` + registry tests pass and overrides work.
2. Per-symbol resolution via heuristics + override surfaced in Settings (Tasks 2–3, 9, 12). 
3. Snapshots labeled as-of on closed markets, in AI payload + UI (Tasks 13–15, 25).
4. Analytics forward returns are trading-day-accurate with honest coverage gaps (Task 16, 26).
5. Observer + trigger gates resolve from watchlist (Tasks 17–19).
6. Relative-to-close mode self-adjusts to half-days (Tasks 20–23).
7. Multi-calendar status visible in the UI (Tasks 10–11, 24).

## Notes for the executor

- **Verify non-NYSE mcal ids first** (see Environment notes). If `SIFMA_US`/`CFE`/`JPX`/`LSE`/`24/7` differ in the installed version, fix `MARKETS` in Task 1 — every later task depends on it.
- **Run migrations** after Tasks 8, 13, 20 and commit the generated files.
- `is_early_close` in Task 4 is a deliberately simple heuristic ("session shorter than 6.5h ⇒ early close"). Keep the behavior the half-day tests pin.
- **E2E/visual/a11y (deferred follow-up):** the spec (§10) calls for E2E lane coverage of the new surfaces. Per-task vitest + backend integration tests already exercise behavior; adding Playwright/visual/a11y cases for the TopNav badge, snapshot closed-banner, Settings override card, and schedule fire-mode form is a recommended follow-up in the `e2e/ui`, `e2e/visual`, and `e2e/a11y` lanes (see `e2e/README.md`). Not required to ship the phases.
- After all phases, consider `superpowers:finishing-a-development-branch` to open the PR.

