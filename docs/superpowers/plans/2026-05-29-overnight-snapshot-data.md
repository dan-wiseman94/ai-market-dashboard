# Overnight Snapshot Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `Snapshot.overnight` mode so a pre-market capture pulls extended-hours/overnight data (wider OHLC window, quote gap context, overnight-scoped news) and a new futures/overseas board section, instead of silently showing yesterday's regular session.

**Architecture:** A persisted boolean flag threads from the capture API through `capture_task` → `capture_for_existing`. When set, the section loop appends an `"overnight"` board section and switches the `ohlc`/`quotes`/`news` fetchers into extended-hours variants; every behavior is dead unless the flag is true, so the shared observer/trigger/briefing capture path is unchanged. The board reuses the `breadth` "curated symbols, silent per-symbol degrade" pattern and reaches the AI through the markdown serializer.

**Tech Stack:** Django + DRF, Celery, Postgres, pandas-market-calendars, the Schwab client, React + TanStack Query + Vitest, Playwright E2E. Everything runs in Docker.

**Spec:** `docs/superpowers/specs/2026-05-29-overnight-snapshot-data-design.md`

**Conventions for every task:**
- Run backend tests **inside the container**, paths dropping the `backend/` prefix (WORKDIR is `/app/backend`): `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<test> -v`
- Run frontend tests in the container: `docker compose exec frontend pnpm exec vitest run src/__tests__/<File>.test.tsx -t "<name>"`
- Every commit message ends with the repo trailer on its own line:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Patch fetchers **at their consumption site** in tests (`apps.snapshots.services.<name>`) — `services/__init__.py` binds these names at import time, so patching the source module does not intercept the `_FETCHERS` lambdas.

---

### Task 1: Model flag, section-kind choice, serializer field, queryset filter, migrations

**Files:**
- Modify: `backend/apps/snapshots/models.py` (add `Snapshot.overnight`; add `("overnight", "Overnight board")` to `SnapshotSection.KIND_CHOICES`)
- Modify: `backend/apps/snapshots/serializers.py` (expose `overnight` on both serializers)
- Modify: `backend/apps/snapshots/views.py:46-59` (`get_queryset` overnight filter)
- Create: `backend/apps/snapshots/migrations/0009_snapshot_overnight.py` (generated; latest existing is `0008_backfill_primary_ticker`)
- Test: `backend/apps/snapshots/tests/test_overnight_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_overnight_model.py`:

```python
import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializers import SnapshotListSerializer, SnapshotSerializer


@pytest.mark.django_db
def test_overnight_defaults_false_and_serializes():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=[])
    assert snap.overnight is False
    assert SnapshotSerializer(snap).data["overnight"] is False
    assert SnapshotListSerializer(snap).data["overnight"] is False


@pytest.mark.django_db
def test_overnight_section_kind_allowed():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["overnight"], overnight=True)
    sec = SnapshotSection.objects.create(snapshot=snap, kind="overnight", payload={}, status="done")
    sec.full_clean()  # choices validation must pass
    assert sec.kind == "overnight"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_overnight_model.py -v`
Expected: FAIL — `Snapshot() got unexpected keyword 'overnight'` / `overnight` not in serializer data.

- [ ] **Step 3: Add the model field and section-kind choice**

In `backend/apps/snapshots/models.py`, add to `SnapshotSection.KIND_CHOICES` (after `("image", "Chart image")`):

```python
        ("overnight", "Overnight board"),
```

In the `Snapshot` model, after the `primary_ticker` field, add:

```python
    overnight = models.BooleanField(default=False, db_index=True)
```

- [ ] **Step 4: Expose `overnight` on both serializers**

In `backend/apps/snapshots/serializers.py`, add `"overnight"` to the `fields` list of **both** `SnapshotListSerializer.Meta.fields` (after `"primary_ticker"`) and `SnapshotSerializer.Meta.fields` (after `"primary_ticker"`).

- [ ] **Step 5: Add the queryset filter**

In `backend/apps/snapshots/views.py`, inside `get_queryset`, after the `source` filter block, add:

```python
        if p.get("overnight") in ("true", "1"):
            qs = qs.filter(overnight=True)
```

- [ ] **Step 6: Generate the migration**

Run: `docker compose exec web python manage.py makemigrations snapshots`
Expected: a new migration adding `Snapshot.overnight` and altering `SnapshotSection.kind` choices (choices change is a no-op `AlterField` on Postgres). Open the generated file and confirm it contains `AddField(... name="overnight" ...)` and an `AlterField` on `kind` — no data migration, fully reversible.

- [ ] **Step 7: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_overnight_model.py apps/snapshots/tests/test_list_endpoint.py apps/snapshots/tests/test_serializer.py -v`
Expected: PASS (new tests pass; existing serializer/list tests still pass).

- [ ] **Step 8: Commit**

```bash
git add backend/apps/snapshots/models.py backend/apps/snapshots/serializers.py backend/apps/snapshots/views.py backend/apps/snapshots/migrations/ backend/apps/snapshots/tests/test_overnight_model.py
git commit -m "feat(snapshots): add Snapshot.overnight flag + overnight section kind"
```

---

### Task 2: `fetch_ohlc_overnight` + `_overnight_window` (market service)

**Files:**
- Modify: `backend/apps/market/services/ohlc.py`
- Test: `backend/apps/market/tests/test_services_ohlc_overnight.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_services_ohlc_overnight.py`:

```python
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.ohlc import _overnight_window, fetch_ohlc_overnight


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


# 2026-05-28 is a regular Thursday NYSE session (EDT, UTC-4):
#   open 09:30 ET = 13:30 UTC, close 16:00 ET = 20:00 UTC
_THU_OPEN = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)


def test_overnight_window_premarket_spans_prior_session_open_to_now():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)  # Fri 08:00 ET, pre-market
    assert _overnight_window("SPY", at=now) == (_THU_OPEN, now)


def test_overnight_window_postmarket_starts_at_todays_open():
    now = datetime(2026, 5, 28, 21, 0, tzinfo=UTC)  # Thu 17:00 ET, after close
    assert _overnight_window("SPY", at=now) == (_THU_OPEN, now)


@pytest.mark.django_db
def test_fetch_ohlc_overnight_requests_extended_hours_no_close_clamp():
    start = _THU_OPEN
    end = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    in_window = int(datetime(2026, 5, 29, 2, 0, tzinfo=UTC).timestamp() * 1000)  # overnight
    out_of_window = int(datetime(2026, 5, 29, 13, 0, tzinfo=UTC).timestamp() * 1000)
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
        patch("apps.market.services.ohlc._overnight_window", return_value=(start, end)),
    ):
        bars = fetch_ohlc_overnight("SPY", timeframe="5m")

    assert len(bars) == 1  # out-of-window candle clamped away
    _, kwargs = client.get_price_history_every_five_minutes.call_args
    assert kwargs["need_extended_hours_data"] is True
    assert kwargs["start_datetime"] == start
    assert kwargs["end_datetime"] == end


@pytest.mark.django_db
def test_fetch_ohlc_overnight_falls_back_to_session_when_no_window():
    with (
        patch("apps.market.services.ohlc._overnight_window", return_value=None),
        patch(
            "apps.market.services.ohlc._fetch_session_from_schwab",
            return_value=[{"ts": "x", "close": 9}],
        ) as fallback,
    ):
        assert fetch_ohlc_overnight("SPY", timeframe="5m") == [{"ts": "x", "close": 9}]
    fallback.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_overnight.py -v`
Expected: FAIL — `cannot import name '_overnight_window'` / `fetch_ohlc_overnight`.

- [ ] **Step 3: Implement the window + fetch functions**

In `backend/apps/market/services/ohlc.py`, after `fetch_ohlc_session` (before `_rows_from_candles`), add:

```python
def fetch_ohlc_overnight(ticker: str, *, timeframe: str) -> list[dict]:
    """Intraday OHLC spanning the prior session's open through now, extended hours
    included and never clamped to the regular close.

    For a pre-market capture this yields one continuous series: the prior regular
    session + after-hours + overnight + this morning's pre-market. Use this for
    overnight-mode snapshot capture only.
    """
    if timeframe not in _METHOD_BY_TIMEFRAME:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    ticker = normalize_symbol(ticker)
    return cache.get_or_fetch(
        f"market:ohlc:{ticker}:{timeframe}:overnight",
        ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
        fetcher=lambda: _fetch_overnight_from_schwab(ticker, timeframe),
    )


def _overnight_window(ticker: str, *, at: datetime | None = None) -> tuple[datetime, datetime] | None:
    """(start, now) UTC: start = the regular open of the most-recently-closed
    session at/before `at`; end = `at`. None when no session falls in the lookback.
    """
    now = at or timezone.now()
    cal = get_market_calendar(calendar_for(ticker))
    try:
        sched = cal.schedule(
            start_date=(now - timedelta(days=7)).date(),
            end_date=(now + timedelta(days=1)).date(),
        )
    except Exception as exc:  # mcal can raise on odd ranges; treat as no data
        log.warning("ohlc.overnight_window schedule failed for %s: %s", ticker, exc)
        return None
    start = None
    for _idx, row in sched.iterrows():
        if row["market_close"].to_pydatetime() <= now:  # latest session already closed
            start = row["market_open"].to_pydatetime()
    if start is None:
        return None
    return start, now


def _fetch_overnight_from_schwab(ticker: str, timeframe: str) -> list[dict]:
    window = _overnight_window(ticker)
    if window is None:
        return _fetch_session_from_schwab(ticker, timeframe, 60)
    start_dt, end_dt = window
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/market/tests/test_services_ohlc_overnight.py apps/market/tests/test_services_ohlc.py -v`
Expected: PASS (new tests pass; existing OHLC tests unaffected).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/ohlc.py backend/apps/market/tests/test_services_ohlc_overnight.py
git commit -m "feat(market): fetch_ohlc_overnight spanning prior-session open through now"
```

---

### Task 3: `fetch_quotes(gap_context=True)` + mock-client fields

**Files:**
- Modify: `backend/apps/market/services/quotes.py`
- Modify: `backend/apps/market/schwab_client.py` (`_MockClient.get_quotes` extra fields)
- Test: `backend/apps/market/tests/test_services_quotes_gap.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_services_quotes_gap.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.quotes import fetch_quotes


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


def _schwab_resp(quote_extra: dict, regular: dict | None = None):
    resp = MagicMock()
    blob = {"quote": {"lastPrice": 100.0, "bidPrice": 99.9, "askPrice": 100.1,
                      "totalVolume": 1000, "highPrice": 101.0, "lowPrice": 99.0,
                      "netPercentChange": 0.5, **quote_extra}}
    if regular is not None:
        blob["regular"] = regular
    resp.json.return_value = {"SPY": blob}
    return resp


@pytest.mark.django_db
def test_gap_context_adds_prior_close_and_gap_pct():
    client = MagicMock()
    client.get_quotes.return_value = _schwab_resp(
        {"closePrice": 98.0, "mark": 100.05, "securityStatus": "Normal"},
        regular={"regularMarketLastPrice": 98.5},
    )
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        out = fetch_quotes(["SPY"], gap_context=True)
    q = out["SPY"]
    assert q["prior_close"] == 98.0
    assert q["regular_last"] == 98.5
    assert q["mark"] == 100.05
    assert q["security_status"] == "Normal"
    assert round(q["gap_pct"], 2) == 2.04  # (100-98)/98*100


@pytest.mark.django_db
def test_gap_context_tolerates_missing_fields():
    client = MagicMock()
    client.get_quotes.return_value = _schwab_resp({})  # no closePrice/regular block
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        out = fetch_quotes(["SPY"], gap_context=True)
    q = out["SPY"]
    assert q["prior_close"] is None
    assert q["gap_pct"] is None
    assert q["regular_last"] is None


@pytest.mark.django_db
def test_default_quotes_unchanged_no_gap_keys():
    client = MagicMock()
    client.get_quotes.return_value = _schwab_resp({"closePrice": 98.0})
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        out = fetch_quotes(["SPY"])  # gap_context defaults False
    assert set(out["SPY"]) == {"last", "bid", "ask", "volume", "high", "low", "pct_change"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_services_quotes_gap.py -v`
Expected: FAIL — `fetch_quotes() got an unexpected keyword argument 'gap_context'`.

- [ ] **Step 3: Implement gap context in `quotes.py`**

Replace `fetch_quotes` and `_fetch_from_schwab` in `backend/apps/market/services/quotes.py` with:

```python
def fetch_quotes(tickers: Iterable[str], *, gap_context: bool = False) -> dict[str, dict]:
    """Return {ticker: {last, bid, ask, volume, high, low, pct_change}} keyed by ticker.

    With ``gap_context=True`` each value also carries ``prior_close``, ``regular_last``,
    ``mark``, ``security_status`` and a computed ``gap_pct`` — for pre-market reads.
    Cached in Redis for 5s (separate key per gap/non-gap so payloads don't collide).
    """
    ticker_list = sorted({normalize_symbol(t) for t in tickers if t})
    if not ticker_list:
        return {}
    suffix = ":gap" if gap_context else ""
    return cache.get_or_fetch(
        f"market:quotes:{','.join(ticker_list)}{suffix}",
        ttl_seconds=cache.ttl_for_kind("quotes"),
        fetcher=lambda: _fetch_from_schwab(ticker_list, gap_context=gap_context),
    )


def _fetch_from_schwab(tickers: list[str], *, gap_context: bool = False) -> dict[str, dict]:
    client = get_schwab_client()
    raw = schwab_json(client.get_quotes(tickers))
    out: dict[str, dict] = {}
    for t, blob in raw.items():
        if not isinstance(blob, dict) or "quote" not in blob:
            continue
        q = blob["quote"]
        row = {
            "last": q.get("lastPrice"),
            "bid": q.get("bidPrice"),
            "ask": q.get("askPrice"),
            "volume": q.get("totalVolume"),
            "high": q.get("highPrice"),
            "low": q.get("lowPrice"),
            "pct_change": q.get("netPercentChange"),
        }
        if gap_context:
            reg = blob.get("regular") or {}
            prior_close = q.get("closePrice")
            last = row["last"]
            gap_pct = None
            if (
                isinstance(prior_close, int | float)
                and prior_close
                and isinstance(last, int | float)
            ):
                gap_pct = (last - prior_close) / prior_close * 100
            row.update(
                {
                    "prior_close": prior_close,
                    "regular_last": reg.get("regularMarketLastPrice"),
                    "mark": q.get("mark"),
                    "security_status": q.get("securityStatus"),
                    "gap_pct": gap_pct,
                }
            )
        out[t] = row
    return out
```

- [ ] **Step 4: Extend the mock client so MOCK_EXTERNAL exercises gap context**

In `backend/apps/market/schwab_client.py`, in `_MockClient.get_quotes`, replace the per-ticker dict so the canned quote includes the gap fields and a `regular` block:

```python
    def get_quotes(self, tickers):
        self._gate()
        return _mock_resp(
            {
                t: {
                    "quote": {
                        "lastPrice": 100.0,
                        "bidPrice": 99.9,
                        "askPrice": 100.1,
                        "totalVolume": 1_000_000,
                        "highPrice": 101.0,
                        "lowPrice": 99.0,
                        "netPercentChange": 0.5,
                        "closePrice": 98.0,
                        "mark": 100.05,
                        "securityStatus": "Normal",
                    },
                    "regular": {"regularMarketLastPrice": 98.5},
                }
                for t in tickers
            }
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/market/tests/test_services_quotes_gap.py apps/market/tests/test_services_quotes.py apps/market/tests/test_schwab_client.py -v`
Expected: PASS (new tests pass; existing quote/mock tests still pass — the extra fields are additive).

- [ ] **Step 6: Commit**

```bash
git add backend/apps/market/services/quotes.py backend/apps/market/schwab_client.py backend/apps/market/tests/test_services_quotes_gap.py
git commit -m "feat(market): fetch_quotes gap_context (prior_close/gap_pct/status)"
```

---

### Task 4: Overnight news lookback helper

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (add `_overnight_news_lookback_hours`; `import math`)
- Test: `backend/apps/snapshots/tests/test_overnight_news_lookback.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_overnight_news_lookback.py`:

```python
from datetime import UTC, datetime

from apps.snapshots.services import _overnight_news_lookback_hours


def test_lookback_rounds_up_hours_since_close():
    as_of = datetime(2026, 5, 28, 20, 0, tzinfo=UTC)  # prior close
    now = datetime(2026, 5, 29, 12, 30, tzinfo=UTC)  # 16.5h later
    assert _overnight_news_lookback_hours(as_of, now=now) == 17


def test_lookback_clamped_to_floor_1():
    as_of = datetime(2026, 5, 29, 11, 59, tzinfo=UTC)
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)  # 1 minute
    assert _overnight_news_lookback_hours(as_of, now=now) == 1


def test_lookback_clamped_to_ceiling_48():
    as_of = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)  # >48h ago (long weekend/holiday)
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    assert _overnight_news_lookback_hours(as_of, now=now) == 48
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_overnight_news_lookback.py -v`
Expected: FAIL — `cannot import name '_overnight_news_lookback_hours'`.

- [ ] **Step 3: Implement the helper**

In `backend/apps/snapshots/services/__init__.py`, add `import math` to the imports, and add this function near `_pick_ticker`:

```python
def _overnight_news_lookback_hours(as_of, *, now=None) -> int:
    """Hours from the prior session close (`as_of`) to now, rounded up, clamped [1, 48]."""
    now = now or timezone.now()
    hours = math.ceil((now - as_of).total_seconds() / 3600)
    return max(1, min(48, hours))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/snapshots/tests/test_overnight_news_lookback.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tests/test_overnight_news_lookback.py
git commit -m "feat(snapshots): overnight news lookback helper (hours since prior close)"
```

---

### Task 5: Futures / overseas board service

**Files:**
- Create: `backend/apps/market/services/overnight.py`
- Test: `backend/apps/market/tests/test_services_overnight_board.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_services_overnight_board.py`:

```python
from unittest.mock import patch

from apps.market.services.overnight import overnight_board


def test_board_groups_symbols_and_drops_unquoted():
    # fetch_quotes returns only the symbols Schwab quoted (others already dropped upstream).
    fake = {
        "/ES": {"last": 5000.0, "gap_pct": 0.5},
        "/VX": {"last": 14.0, "gap_pct": -1.0},
        "$DAX": {"last": 18000.0, "gap_pct": 0.2},
    }
    with patch("apps.market.services.overnight.fetch_quotes", return_value=fake) as fq:
        board = overnight_board()
    # gap context must be requested
    assert fq.call_args.kwargs.get("gap_context") is True
    assert board["futures"]["/ES"]["last"] == 5000.0
    assert board["vol_rates"]["/VX"]["gap_pct"] == -1.0
    assert board["overseas"]["$DAX"]["last"] == 18000.0
    # Symbols Schwab didn't quote (e.g. /NQ) simply don't appear.
    assert "/NQ" not in board["futures"]


def test_board_empty_groups_when_nothing_quoted():
    with patch("apps.market.services.overnight.fetch_quotes", return_value={}):
        board = overnight_board()
    assert board == {"futures": {}, "vol_rates": {}, "overseas": {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_services_overnight_board.py -v`
Expected: FAIL — `No module named 'apps.market.services.overnight'`.

- [ ] **Step 3: Implement the board service**

Create `backend/apps/market/services/overnight.py`:

```python
"""Overnight board: index futures + vol/rates + overseas cash indices.

Reuses the breadth pattern — fetch a curated symbol set in one batched call and
silently drop any symbol Schwab won't quote. Overseas-index symbology on Schwab
is partial; unresolved symbols just don't appear in the board.
"""

from __future__ import annotations

from apps.market.services.quotes import fetch_quotes

US_INDEX_FUTURES = ["/ES", "/NQ", "/YM", "/RTY"]
VOL_RATES = ["/VX", "/ZN"]
# Best-effort overseas cash indices; verify/adjust symbols against live Schwab
# responses. Unresolved symbols are dropped (see module docstring).
OVERSEAS = ["$NIKK", "$HSI", "$UKX", "$DAX", "$SX5E"]


def overnight_board() -> dict:
    """{"futures": {...}, "vol_rates": {...}, "overseas": {...}} keyed by symbol,
    each value a gap-context quote dict. Missing symbols are omitted."""
    quotes = fetch_quotes(US_INDEX_FUTURES + VOL_RATES + OVERSEAS, gap_context=True)

    def group(symbols: list[str]) -> dict:
        return {s: quotes[s] for s in symbols if s in quotes}

    return {
        "futures": group(US_INDEX_FUTURES),
        "vol_rates": group(VOL_RATES),
        "overseas": group(OVERSEAS),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/market/tests/test_services_overnight_board.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/overnight.py backend/apps/market/tests/test_services_overnight_board.py
git commit -m "feat(market): overnight_board (futures + vol/rates + overseas)"
```

---

### Task 6: Capture wiring — thread the flag, branch the fetchers, append the board

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (imports, fetchers, `capture_for_existing`, `capture`)
- Modify: `backend/apps/snapshots/tasks.py` (`overnight` kwarg)
- Modify: `backend/apps/snapshots/views.py:61-92` (`create` reads + forwards `overnight`)
- Test: `backend/apps/snapshots/tests/test_capture_overnight.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_capture_overnight.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_overnight_capture_enriches_sections_and_adds_board():
    profile = TradingProfile.objects.create(name="P", style="x")
    quotes_mock = MagicMock(return_value={"SPY": {"last": 100.0, "gap_pct": 2.0, "prior_close": 98.0}})
    with (
        patch("apps.snapshots.services.fetch_quotes", quotes_mock),
        patch(
            "apps.snapshots.services.fetch_ohlc_overnight",
            return_value=[{"ts": "2026-05-29T02:00:00+00:00", "open": 1, "high": 2,
                           "low": 1, "close": 1.5, "volume": 10}],
        ),
        patch("apps.snapshots.services.fetch_news",
              return_value=[{"id": 1, "headline": "overnight h", "datetime": 1_700_000_000}]),
        patch("apps.snapshots.services.overnight_board",
              return_value={"futures": {"/ES": {"last": 5000.0, "gap_pct": 0.5}},
                            "vol_rates": {}, "overseas": {}}),
    ):
        snap = capture(
            profile=profile, objective="o",
            includes=["quotes", "ohlc", "news"],
            watchlist_tickers=["SPY"], ohlc_ticker="SPY", ohlc_timeframe="1m",
            overnight=True,
        )

    assert snap.overnight is True
    assert "overnight" in snap.includes
    secs = {s.kind: s for s in snap.sections.all()}
    # board section created + done
    assert secs["overnight"].status == "done"
    assert secs["overnight"].payload["futures"]["/ES"]["last"] == 5000.0
    # quotes asked for gap context, gap fields present
    assert quotes_mock.call_args.kwargs.get("gap_context") is True
    assert secs["quotes"].payload["SPY"]["gap_pct"] == 2.0
    # ohlc widened + coarsened 1m -> 5m + window tag
    assert secs["ohlc"].payload["window"] == "overnight"
    assert secs["ohlc"].payload["timeframe"] == "5m"
    # news tagged overnight with a since timestamp
    assert secs["news"].payload["window"] == "overnight"
    assert "since" in secs["news"].payload


@pytest.mark.django_db
def test_default_capture_unchanged_when_overnight_false():
    profile = TradingProfile.objects.create(name="P", style="x")
    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 100.0}}),
        patch("apps.snapshots.services.fetch_ohlc_session", return_value=[]),
    ):
        snap = capture(
            profile=profile, objective="o",
            includes=["quotes", "ohlc"],
            watchlist_tickers=["SPY"], ohlc_ticker="SPY", ohlc_timeframe="1m",
        )
    assert snap.overnight is False
    assert "overnight" not in snap.includes
    secs = {s.kind: s for s in snap.sections.all()}
    assert "window" not in secs["ohlc"].payload  # not widened
    assert secs["ohlc"].payload["timeframe"] == "1m"  # not coarsened
    assert set(secs["quotes"].payload["SPY"]) == {"last"}  # no gap fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_overnight.py -v`
Expected: FAIL — `capture() got an unexpected keyword argument 'overnight'`.

- [ ] **Step 3: Update imports and the enriched fetchers**

In `backend/apps/snapshots/services/__init__.py`:

(a) Add `fetch_ohlc_overnight` to the ohlc import and import the board + `market_state`:

```python
from apps.market.services.ohlc import (
    SESSION_TIMEFRAMES,
    fetch_ohlc,
    fetch_ohlc_overnight,
    fetch_ohlc_session,
)
from apps.market.services.overnight import overnight_board
```

`market_state` and `calendar_for` are already imported from `apps.market.calendar` (line 11) — leave that import, just ensure `market_state` is in the imported names (it is via `calendar_for, market_state` — if not, add `market_state`).

(b) Replace `_fetch_ohlc_section` to honor `overnight`:

```python
def _fetch_ohlc_section(
    *,
    watchlist_tickers: list[str],
    ohlc_ticker: str | None = None,
    ohlc_timeframe: str = "1m",
    ohlc_bars: int = 60,
    overnight: bool = False,
    **_,
) -> dict:
    ticker = _pick_ticker(ohlc_ticker, watchlist_tickers)
    if overnight:
        # 1m over the ~17h+ overnight window is too many bars; coarsen to 5m.
        tf = "5m" if ohlc_timeframe == "1m" else ohlc_timeframe
        bars = fetch_ohlc_overnight(ticker, timeframe=tf)
        return {"data": {"ticker": ticker, "timeframe": tf, "bars": bars, "window": "overnight"}}
    if ohlc_timeframe in SESSION_TIMEFRAMES:
        bars = fetch_ohlc_session(ticker, timeframe=ohlc_timeframe)
    else:
        bars = fetch_ohlc(ticker, timeframe=ohlc_timeframe, bars=ohlc_bars)
    return {"data": {"ticker": ticker, "timeframe": ohlc_timeframe, "bars": bars}}
```

(c) Add a named news-section fetcher above `_FETCHERS`:

```python
def _fetch_news_section(
    *, watchlist_tickers: list[str], overnight: bool = False, as_of=None, **_
) -> dict:
    tickers = list(watchlist_tickers)
    if overnight and as_of is not None:
        items = fetch_news(tickers, lookback_hours=_overnight_news_lookback_hours(as_of))
        return {"data": {"items": items, "window": "overnight", "since": as_of.isoformat()}}
    return {"data": {"items": fetch_news(tickers)}}
```

(d) In the `_FETCHERS` dict: change the `quotes` and `news` entries and add `overnight`:

```python
    "news": _fetch_news_section,
    "overnight": lambda **_: {"data": overnight_board()},
    ...
    "quotes": lambda *, watchlist_tickers, overnight=False, **_: {
        "data": fetch_quotes(watchlist_tickers, gap_context=overnight)
    },
```

(Leave `ohlc` mapped to `_fetch_ohlc_section`; remove the old inline `news` lambda.)

- [ ] **Step 4: Thread `overnight`/`as_of` through `capture_for_existing` and `capture`**

In `capture_for_existing`, change the signature to add `overnight: bool = False`, and at the top (before the `for kind in snap.includes` loop) add:

```python
    if overnight and "overnight" not in snap.includes:
        snap.includes = [*snap.includes, "overnight"]
        snap.save(update_fields=["includes"])
        snap.overnight = True
        snap.save(update_fields=["overnight"])
    as_of = None
    if overnight:
        rep = _pick_ticker(ohlc_ticker, list(watchlist_tickers))
        as_of = market_state(symbol=rep).as_of
```

In the `fetcher(...)` call inside the loop, add the two kwargs:

```python
            result = fetcher(  # type: ignore[operator]
                snapshot_id=snap.id,
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
                overnight=overnight,
                as_of=as_of,
            )
```

In `capture(...)`, add `overnight: bool = False` to the signature and forward it:

```python
    return capture_for_existing(
        snap,
        watchlist_tickers=watchlist_tickers,
        ohlc_ticker=ohlc_ticker,
        ohlc_timeframe=ohlc_timeframe,
        ohlc_bars=ohlc_bars,
        overnight=overnight,
    )
```

Also set it on the created `Snapshot` in `capture(...)` so a direct `capture(overnight=True)` persists it even before the loop appends the section: add `overnight=overnight,` to the `Snapshot.objects.create(...)` kwargs.

- [ ] **Step 5: Thread it through the Celery task and the view**

In `backend/apps/snapshots/tasks.py`, add `overnight: bool = False` to `capture_task`'s signature and pass `overnight=overnight` into `capture_for_existing(...)`.

In `backend/apps/snapshots/views.py` `create`: set `overnight=bool(data.get("overnight", False))` on the `Snapshot.objects.create(...)` call, and add `overnight=bool(data.get("overnight", False)),` to the `capture_task.delay(...)` kwargs.

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_capture_overnight.py apps/snapshots/tests/test_capture.py apps/snapshots/tests/test_capture_extended.py apps/snapshots/tests/test_tasks.py -v`
Expected: PASS (new overnight + default-unchanged tests pass; existing capture tests unaffected). If `apps/snapshots/tests/test_tasks.py` does not exist, drop it from the command.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/tasks.py backend/apps/snapshots/views.py backend/apps/snapshots/tests/test_capture_overnight.py
git commit -m "feat(snapshots): wire overnight mode through capture (ohlc/quotes/news/board)"
```

---

### Task 7: AI markdown rendering for the new fields

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (`_render_overnight`, `_RENDERERS`, `_title`, `_render_quotes`, `_render_news`, `_render_ohlc`)
- Test: `backend/apps/snapshots/tests/test_serializer_overnight.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_serializer_overnight.py`:

```python
from apps.snapshots.serializer import (
    _render_news,
    _render_ohlc,
    _render_overnight,
    _render_quotes,
)


def test_render_overnight_groups_present_only():
    md = _render_overnight(
        {"futures": {"/ES": {"last": 5000.0, "gap_pct": 0.5, "prior_close": 4975.0}},
         "vol_rates": {}, "overseas": {}}
    )
    assert "## Overnight board" in md
    assert "Index futures" in md
    assert "/ES" in md
    assert "Vol & rates" not in md  # empty group omitted


def test_render_overnight_empty():
    md = _render_overnight({"futures": {}, "vol_rates": {}, "overseas": {}})
    assert "no overnight quotes" in md


def test_render_quotes_adds_gap_columns_when_present():
    md = _render_quotes({"SPY": {"last": 100.0, "pct_change": 0.5, "gap_pct": 2.04, "prior_close": 98.0}})
    assert "Gap%" in md
    assert "PrevClose" in md


def test_render_quotes_no_gap_columns_by_default():
    md = _render_quotes({"SPY": {"last": 100.0, "pct_change": 0.5}})
    assert "Gap%" not in md


def test_render_news_overnight_header():
    md = _render_news({"items": [], "window": "overnight"})
    assert "overnight" in md.lower()


def test_render_ohlc_overnight_header():
    md = _render_ohlc({"ticker": "SPY", "timeframe": "5m", "window": "overnight",
                       "bars": [{"ts": "t", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 9}]})
    assert "overnight" in md.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_serializer_overnight.py -v`
Expected: FAIL — `cannot import name '_render_overnight'`.

- [ ] **Step 3: Implement the renderer changes in `serializer.py`**

(a) Replace `_render_quotes` with a gap-aware version:

```python
def _render_quotes(payload: dict) -> str:
    if not payload:
        return "## Quotes\n_(empty)_"
    has_gap = any(
        isinstance(q, dict) and q.get("gap_pct") is not None for q in payload.values()
    )
    if has_gap:
        head = "| Ticker | Last | %chg | Gap% | PrevClose | Bid | Ask | Vol | High | Low |"
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    else:
        head = "| Ticker | Last | %chg | Bid | Ask | Vol | High | Low |"
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|"
    lines = ["## Quotes", head, sep]
    for ticker, q in payload.items():
        row = f"| {ticker} | {_fmt(q.get('last'))} | {_fmt(q.get('pct_change'))}% |"
        if has_gap:
            row += f" {_fmt(q.get('gap_pct'))}% | {_fmt(q.get('prior_close'))} |"
        row += (
            f" {_fmt(q.get('bid'))} | {_fmt(q.get('ask'))} | {_fmt_int(q.get('volume'))} | "
            f"{_fmt(q.get('high'))} | {_fmt(q.get('low'))} |"
        )
        lines.append(row)
    return "\n".join(lines)
```

(b) Update `_render_ohlc` header (replace the `header =` line):

```python
    header = f"## OHLC ({payload.get('ticker', '?')} @ {payload.get('timeframe', '?')})"
    if payload.get("window") == "overnight":
        header += " — overnight (extended hours)"
```

(c) Update `_render_news` to vary the title (replace the two hardcoded `"## News (last 24h)"` strings):

```python
    overnight = isinstance(payload, dict) and payload.get("window") == "overnight"
    title = "## News (overnight, since the prior close)" if overnight else "## News (last 24h)"
```
then use `title` for both the empty case (`f"{title}\n_(no headlines)_"`) and the header line (`lines = [title, ""]`).

(d) Add `_render_overnight` (place near `_render_breadth`):

```python
def _render_overnight(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    groups = [("Index futures", "futures"), ("Vol & rates", "vol_rates"), ("Overseas", "overseas")]
    out = ["## Overnight board"]
    any_rows = False
    for label, key in groups:
        rows = payload.get(key) or {}
        if not rows:
            continue
        any_rows = True
        out.append(f"### {label}")
        out.append("| Symbol | Last | Gap% | Prev close |")
        out.append("|---|---:|---:|---:|")
        for sym, q in rows.items():
            out.append(
                f"| {sym} | {_fmt(q.get('last'))} | {_fmt(q.get('gap_pct'))}% | "
                f"{_fmt(q.get('prior_close'))} |"
            )
    if not any_rows:
        return "## Overnight board\n_(no overnight quotes available)_"
    return "\n".join(out)
```

(e) Register it in `_title` (add `"overnight": "Overnight board",`) and in `_RENDERERS` (add `"overnight": _render_overnight,`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_serializer_overnight.py apps/snapshots/tests/test_serializer.py apps/snapshots/tests/test_serializer_news.py -v`
Expected: PASS (new tests pass; existing serializer tests still pass — default quotes/news output unchanged).

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_overnight.py
git commit -m "feat(snapshots): AI markdown for overnight board + gap columns + overnight news/ohlc headers"
```

---

### Task 8: Diff support for the overnight board

**Files:**
- Modify: `backend/apps/snapshots/diff.py` (`_diff_overnight`, route in `_diff_one`)
- Test: `backend/apps/snapshots/tests/test_diff_overnight.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_diff_overnight.py`:

```python
import pytest

from apps.snapshots.diff import diff_sections


def test_diff_overnight_reports_moves_above_threshold():
    prev = {"overnight": {"futures": {"/ES": {"last": 5000.0}}, "vol_rates": {}, "overseas": {}}}
    curr = {"overnight": {"futures": {"/ES": {"last": 5050.0}}, "vol_rates": {}, "overseas": {}}}
    md = diff_sections(prev, curr)
    assert "/ES" in md
    assert "1.00%" in md


def test_diff_overnight_ignores_sub_threshold():
    prev = {"overnight": {"futures": {"/ES": {"last": 5000.0}}, "vol_rates": {}, "overseas": {}}}
    curr = {"overnight": {"futures": {"/ES": {"last": 5001.0}}, "vol_rates": {}, "overseas": {}}}
    md = diff_sections(prev, curr)
    assert "below 0.5%" in md


@pytest.mark.parametrize("bad", [None, [], "x", {"futures": "nope"}])
def test_diff_overnight_never_raises_on_bad_shape(bad):
    diff_sections({"overnight": bad}, {"overnight": bad})  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_diff_overnight.py -v`
Expected: FAIL — board diff not implemented (no `/ES` line; `_diff_one` returns `""` for `overnight`).

- [ ] **Step 3: Implement `_diff_overnight` + route it**

In `backend/apps/snapshots/diff.py`, add to `_diff_one` (before the final `return ""`):

```python
    if kind == "overnight":
        return _diff_overnight(_as_dict(prev), _as_dict(curr))
```

And add the function (after `_diff_ohlc`):

```python
def _diff_overnight(prev: dict, curr: dict) -> str:
    rows: list[str] = []
    for group in ("futures", "vol_rates", "overseas"):
        p = _as_dict(prev.get(group))
        c = _as_dict(curr.get(group))
        for sym, cq in c.items():
            if not isinstance(cq, dict):
                continue
            pq = _as_dict(p.get(sym))
            p_last, c_last = pq.get("last"), cq.get("last")
            if p_last is None or c_last is None:
                continue
            try:
                change = (c_last - p_last) / p_last if p_last else 0.0
            except (TypeError, ZeroDivisionError):
                continue
            if abs(change) < _NOISE_PCT:
                continue
            sign = "+" if change >= 0 else ""
            rows.append(f"- {sym}: {p_last:g} → {c_last:g} ({sign}{change * 100:.2f}%)")
    return "\n".join(rows) if rows else "- (overnight board moves below 0.5%)"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_diff_overnight.py apps/snapshots/tests/test_diff.py apps/snapshots/tests/test_diff_deepen.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/diff.py backend/apps/snapshots/tests/test_diff_overnight.py
git commit -m "feat(snapshots): diff_sections branch for the overnight board"
```

---

### Task 9: Frontend — composer toggle, API types, browser badge

**Files:**
- Modify: `frontend/src/api/snapshots.ts` (`overnight` on `Snapshot`, `CreateSnapshotBody`, `SnapshotListRow`)
- Modify: `frontend/src/pages/SnapshotComposerPage.tsx` (toggle + send `overnight`)
- Modify: `frontend/src/pages/snapshots/SnapshotTable.tsx` (overnight badge)
- Test: `frontend/src/__tests__/SnapshotComposerPage.test.tsx` (add one test)

- [ ] **Step 1: Write the failing test**

In `frontend/src/__tests__/SnapshotComposerPage.test.tsx`, add this test inside the main `describe("SnapshotComposerPage", ...)` block:

```tsx
  it("sends overnight: true when the overnight toggle is on", async () => {
    const user = userEvent.setup();
    mockCreateSnap.mockResolvedValue({ id: 100, status: "ready", includes: [] });
    mockCreateThread.mockResolvedValue({ id: 200, title: "Consult" });

    const nav = { captured: "" };
    renderComposer(nav);
    await waitFor(() => {
      const [profileSelect] = screen.getAllByRole("combobox");
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });

    await user.click(screen.getByRole("checkbox", { name: /overnight/i }));
    await user.click(screen.getByTestId("capture-btn"));

    await waitFor(() => {
      expect(mockCreateSnap).toHaveBeenCalledWith(
        expect.objectContaining({ overnight: true }),
      );
    });
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposerPage.test.tsx -t "overnight toggle"`
Expected: FAIL — no checkbox named /overnight/; `overnight` not in the create body.

- [ ] **Step 3: Add `overnight` to the API types**

In `frontend/src/api/snapshots.ts`:
- Add `overnight: boolean;` to the `Snapshot` type.
- Add `overnight?: boolean;` to `CreateSnapshotBody`.
- Add `overnight: boolean;` to `SnapshotListRow`.

- [ ] **Step 4: Add the toggle to the composer**

In `frontend/src/pages/SnapshotComposerPage.tsx`:
- Add state after the `includes` state: `const [overnight, setOvernight] = useState(false);`
- Add `overnight` to the `createSnap.mutateAsync({...})` body (alongside `includes`).
- Add the toggle UI right after the `</div>` that closes the Sections block (after the `SnapshotSectionPicker`):

```tsx
        <div>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={overnight}
              onChange={(e) => setOvernight(e.target.checked)}
              className="accent-emerald-500"
            />
            Overnight (pre-market)
          </label>
          {overnight && (
            <p className="text-xs text-slate-500 mt-1">
              OHLC, quotes, and news shift to extended hours; adds a futures + overseas board.
            </p>
          )}
        </div>
```

- [ ] **Step 5: Add the overnight badge to the browser table**

In `frontend/src/pages/snapshots/SnapshotTable.tsx`, in the Ticker cell, render a badge when `row.overnight`. Replace the ticker `<td>` body with:

```tsx
                <td className="py-2 pr-4 font-mono font-medium text-copper-300">
                  {row.primary_ticker ?? "—"}
                  {row.overnight && (
                    <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-sans bg-indigo-900/40 text-indigo-300 align-middle">
                      overnight
                    </span>
                  )}
                </td>
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposerPage.test.tsx`
Expected: PASS (the new test + all existing composer tests).

- [ ] **Step 7: Typecheck + lint the frontend**

Run: `docker compose exec frontend pnpm run lint`
Expected: PASS (no TS errors from the new `overnight` fields; `SnapshotListRow` consumers compile).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/snapshots.ts frontend/src/pages/SnapshotComposerPage.tsx frontend/src/pages/snapshots/SnapshotTable.tsx frontend/src/__tests__/SnapshotComposerPage.test.tsx
git commit -m "feat(frontend): overnight capture toggle + snapshots-browser badge"
```

---

### Task 10: E2E gold journey

**Files:**
- Create: `e2e/ui/test_snapshots_overnight_gold.py`

- [ ] **Step 1: Write the E2E test**

Create `e2e/ui/test_snapshots_overnight_gold.py`. Mirror the structure of an existing `e2e/ui/*_gold.py` capture journey (open it first for the exact fixtures/helpers — page navigation, the `capture-btn` testid, and the ready-wait). The journey:

```python
"""Overnight capture journey: toggle overnight → capture → board reaches the thread."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_overnight_capture_shows_board(page: Page, app_url: str):
    page.goto(f"{app_url}/compose")
    # Wait for the composer to hydrate (profile auto-selects).
    expect(page.get_by_test_id("capture-btn")).to_be_enabled()

    page.get_by_role("checkbox", name="Overnight (pre-market)").check()
    page.get_by_placeholder("What do you want the AI to consider right now?").fill(
        "Pre-market read"
    )
    page.get_by_test_id("capture-btn").click()

    # Capture + ask navigates to the thread; the serialized snapshot (incl. the
    # Overnight board) is the synthetic first user message under MOCK_EXTERNAL.
    page.wait_for_url("**/threads/**", timeout=60_000)
    expect(page.get_by_text("Overnight board", exact=False)).to_be_visible(timeout=60_000)
```

Adjust selectors to match the conventions in the sibling `_gold.py` files (e.g. how they reach `/compose`, whether a watchlist must be chosen first for the button to enable, and the exact thread-message locator).

- [ ] **Step 2: Run the E2E lane**

Run: `make e2e-one t=ui/test_snapshots_overnight_gold.py` (requires the overlay up: `make e2e-up`)
Expected: PASS — the board text appears in the thread under `MOCK_EXTERNAL`. If the board only renders inside the AI markdown and the mock AI echoes the payload, assert on the snapshot serialization instead (follow whatever the sibling capture gold test asserts on).

- [ ] **Step 3: Commit**

```bash
git add e2e/ui/test_snapshots_overnight_gold.py
git commit -m "test(e2e): overnight capture gold journey"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- §1 model + wiring → Tasks 1, 6. §2 OHLC window → Task 2 (+ coarsening in Task 6). §3 quote gap context → Task 3. §4 overnight news → Tasks 4 + 6. §5 board → Task 5 (+ section wiring in Task 6). §6 serialization/diff/browser → serializer in Task 7, diff in Task 8, serializer `overnight` field + `?overnight=` filter in Task 1, browser badge in Task 9. §7 frontend → Task 9. §8 mocks/tests → mock fields in Task 3; tests throughout. §9 migrations/ops → Task 1.
- **Deviation (recorded):** the spec §7 "detail renderer" is satisfied by the AI markdown renderer (`_render_overnight`, Task 7) — the post-capture surface is the thread view, which renders the serialized snapshot markdown; a bespoke React board table would be redundant, so it is intentionally omitted (YAGNI). The browser badge (Task 9) is included; the optional UI filter *chip* is dropped in favor of the already-implemented server-side `?overnight=true` filter (Task 1) — wire a chip later if desired.

**2. Placeholder scan** — no "TBD/handle errors/similar to". The one external unknown (Schwab overseas-index symbols) is an explicit best-effort constant with silent degrade, tested in Task 5.

**3. Type/signature consistency** — verified across tasks: `fetch_quotes(tickers, *, gap_context=False)` (Tasks 3, 5, 6); `fetch_ohlc_overnight(ticker, *, timeframe)` (Tasks 2, 6); `overnight_board()` returning `{futures, vol_rates, overseas}` (Tasks 5, 6, 7, 8); `_overnight_news_lookback_hours(as_of, *, now=None)` (Tasks 4, 6); `capture(..., overnight=False)` / `capture_for_existing(..., overnight=False)` / `capture_task(..., overnight=False)` (Task 6); section kind `"overnight"` and payload key `"window"` consistent across capture (Task 6), serializer (Task 7), and diff (Task 8).
