# M16 P1 — Data Layer + Signals Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the input history (IV scalars, short interest, breadth, news sentiment) and build the single signal engine (`compute_signals`) with four family modules, so later phases can route signals into snapshots, triggers, analytics, and regime/coverage.

**Architecture:** Three new append-only models + one new `NewsItem` column feed a new pure-math package `backend/apps/market/services/signals/` (engine + four family modules + bundles), backed by new module-level primitives in `apps/market/services/indicator.py`. Two new beat tasks (`market.ingest_iv_summary`, `market.refresh_short_interest`) plus a deepened `market.ingest_daily_bars` (bars=300 + BreadthDaily rider) build the history; a keyless FINRA client and two Finnhub free-tier fetchers supply positioning data. Nothing consumes the engine yet — P1 is independently shippable.

**Tech Stack:** Django 5 / DRF, Celery beat, Redis (`apps/market/cache.py`), `requests` provider clients, pytest + Hypothesis.

**Spec:** docs/superpowers/specs/2026-07-05-strategy-signals-design.md (§3, §5, §6, §9, §10)

## Global Constraints

Repo global constraints (from the pinned M16 interface contract — its names/signatures are law):

- Everything runs in Docker. One backend test:
  `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (WORKDIR /app/backend).
  One FE test: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`. Lint: `make lint`.
- Never set MOCK_EXTERNAL on the dev stack.
- Migrations gated by `make check-migrations`; beat tasks inventoried in `apps/core/scheduled_tasks.py`
  in the SAME commit (drift gate); worker/beat need `docker compose restart worker beat` after task changes.
- OpenAPI: `make schema` regenerates backend/schema.yml (commit it); `pnpm gen:api` runs on the HOST
  (broken inside the frontend container).
- DRF exposes FK ids as `*_id`. Section terminal state "done"; parent Snapshot "ready".
- Never log provider exceptions raw when the key rides in the URL — use `safe_err`.
- New FE components ship with co-located `*.stories.tsx` (storyless ratchet at ceiling) and a vitest test.
- Conventional commits (`feat(market):`, `feat(observer):`, `feat(frontend):`, `test:`, `docs:`); frequent.
- CI gate runs pytest `-p no:randomly`; coverage floors backend 86 branch, FE 80/74/77/82; ruff C901 ≤15.

P1-specific constraints:

- **Scope fence:** touch only `apps/market`, `apps/core` (retention + scheduled-tasks wiring), `config/celery.py`, `config/settings/base.py`, and the minimal `apps/secrets` surface the FINRA deliverable requires (catalog entry, probe, keyless-test wiring). No FE changes, no snapshot/trigger/analytics changes — those are P2–P5.
- **Absent, never invented; degrade, never raise** (spec §9): every provider client returns `[]`/`{}`/`None` on failure; every signal is `None` on missing inputs; the engine never raises.
- Every new Redis cache kind MUST be registered in `apps/market/cache.py::_TTL` (unregistered kinds silently default to 30s and hammer free APIs).
- No milestone tags / "new in M16" / version-history framing in code comments — present-tense invariants only.
- Provider tests mock at the module's `_get`/`_post` boundary with `unittest.mock.patch` + the cache-passthrough pattern (`side_effect=lambda key, *, ttl_seconds, fetcher: fetcher()`), matching every sibling provider test (the clients use `requests`, so httpx-only `respx` does not apply here).
- FINRA is NOT added to the import-linter `forbidden_modules` list (pyproject.toml:230-237): like edgar/fred/treasury it is a distinct data domain, not a fungible quote vendor, and P1 consumes it only inside `apps.market`.

---

### Task 1: Models — IVDaily, ShortInterestRecord, BreadthDaily, NewsItem.sentiment (+ migration)

**Files:**
- Modify: `backend/apps/market/models.py` (append after `Theme`, line 213; add `sentiment` to `NewsItem` after `published_at`, line 59)
- Create: `backend/apps/market/migrations/0010_*.py` (generated)
- Test: `backend/apps/market/tests/test_signal_history_models.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces (exact — the contract file pins these):
  ```python
  class IVDaily:            # unique (ticker, date); index (ticker, -date)
      ticker: CharField(max_length=12); date: DateField()
      atm_iv, term_slope, put_call_vol, put_call_oi, gex_total, flip_strike, hv_20: FloatField(null=True)

  class ShortInterestRecord:  # unique (ticker, settlement_date); index (ticker, -settlement_date)
      ticker: CharField(max_length=12); settlement_date: DateField()
      shares_short: BigIntegerField(null=True); avg_daily_volume: BigIntegerField(null=True)
      days_to_cover: FloatField(null=True)

  class BreadthDaily:       # date unique
      date: DateField(unique=True)
      advn_close, decn_close, net_ad: FloatField(null=True)

  NewsItem.sentiment: FloatField(null=True)   # per-ticker Marketaux score, null elsewhere
  ```

**Steps:**

- [ ] Write the failing test file `backend/apps/market/tests/test_signal_history_models.py`:

```python
"""Model contracts for the signal input-history tables (IVDaily,
ShortInterestRecord, BreadthDaily) + NewsItem.sentiment."""

from __future__ import annotations

from datetime import date, datetime, timezone as dt_timezone

import pytest
from django.db import IntegrityError

from apps.market.models import BreadthDaily, IVDaily, NewsItem, ShortInterestRecord


@pytest.mark.django_db
def test_ivdaily_unique_on_ticker_date():
    IVDaily.objects.create(ticker="AAPL", date=date(2026, 7, 1), atm_iv=25.0)
    with pytest.raises(IntegrityError):
        IVDaily.objects.create(ticker="AAPL", date=date(2026, 7, 1), atm_iv=26.0)


@pytest.mark.django_db
def test_ivdaily_all_scalars_nullable():
    row = IVDaily.objects.create(ticker="AAPL", date=date(2026, 7, 1))
    row.refresh_from_db()
    assert row.atm_iv is None
    assert row.term_slope is None
    assert row.put_call_vol is None
    assert row.put_call_oi is None
    assert row.gex_total is None
    assert row.flip_strike is None
    assert row.hv_20 is None


@pytest.mark.django_db
def test_short_interest_unique_on_ticker_settlement_date():
    ShortInterestRecord.objects.create(
        ticker="GME", settlement_date=date(2026, 6, 30), shares_short=1_000_000
    )
    with pytest.raises(IntegrityError):
        ShortInterestRecord.objects.create(ticker="GME", settlement_date=date(2026, 6, 30))


@pytest.mark.django_db
def test_breadth_daily_date_unique():
    BreadthDaily.objects.create(date=date(2026, 7, 1), advn_close=2000.0, decn_close=800.0, net_ad=1200.0)
    with pytest.raises(IntegrityError):
        BreadthDaily.objects.create(date=date(2026, 7, 1))


@pytest.mark.django_db
def test_newsitem_sentiment_nullable_default_none():
    item = NewsItem.objects.create(
        provider="finnhub",
        external_id="x1",
        headline="h",
        url="https://example.com/x",
        published_at=datetime(2026, 7, 1, tzinfo=dt_timezone.utc),
    )
    item.refresh_from_db()
    assert item.sentiment is None
    item.sentiment = 0.42
    item.save()
    item.refresh_from_db()
    assert item.sentiment == pytest.approx(0.42)
```

- [ ] Run it — expect ImportError (models don't exist yet):

```bash
docker compose exec web pytest apps/market/tests/test_signal_history_models.py -v
# EXPECTED: ImportError: cannot import name 'BreadthDaily' from 'apps.market.models'
```

- [ ] Implement. In `backend/apps/market/models.py`, add the `sentiment` field to `NewsItem` — after line 59 (`published_at = models.DateTimeField(db_index=True)`) insert:

```python
    # Per-ticker sentiment score from Marketaux (the row's primary ticker).
    # Finnhub/Tiingo news never set it — all readers must be null-safe.
    sentiment = models.FloatField(null=True, blank=True)
```

- [ ] Append the three new models at the end of `backend/apps/market/models.py` (after the `Theme` class, line 213):

```python
class IVDaily(models.Model):
    """One compact row of chain-derived volatility scalars per (ticker, date).

    Distilled nightly by ``market.ingest_iv_summary`` from ``chain_analytics()``
    + stored closes. This is the input history behind 252-day IV rank/percentile —
    full-chain JSONB (``OptionChainSnapshot``, 120d retention) cannot back it.
    No chain source for a ticker → no row (silent), never invented values.
    """

    ticker = models.CharField(max_length=12)
    date = models.DateField()
    atm_iv = models.FloatField(null=True, blank=True)
    term_slope = models.FloatField(null=True, blank=True)
    put_call_vol = models.FloatField(null=True, blank=True)
    put_call_oi = models.FloatField(null=True, blank=True)
    gex_total = models.FloatField(null=True, blank=True)
    flip_strike = models.FloatField(null=True, blank=True)
    hv_20 = models.FloatField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["ticker", "date"], name="uniq_ivdaily_ticker_date"),
        ]
        indexes: ClassVar = [models.Index(fields=["ticker", "-date"])]

    def __str__(self) -> str:
        return f"IVDaily({self.ticker}, {self.date})"


class ShortInterestRecord(models.Model):
    """One FINRA consolidated short-interest report per (ticker, settlement_date).

    Published ~twice monthly; upserted daily by ``market.refresh_short_interest``
    (a no-op unless a new settlement date appeared). All values nullable — FINRA
    rows can omit fields; absent, never invented.
    """

    ticker = models.CharField(max_length=12)
    settlement_date = models.DateField()
    shares_short = models.BigIntegerField(null=True, blank=True)
    avg_daily_volume = models.BigIntegerField(null=True, blank=True)
    days_to_cover = models.FloatField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["ticker", "settlement_date"], name="uniq_shortinterest_ticker_date"
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["ticker", "-settlement_date"])]

    def __str__(self) -> str:
        return f"ShortInterestRecord({self.ticker}, {self.settlement_date})"


class BreadthDaily(models.Model):
    """One row per session of NYSE advance/decline closes ($ADVN/$DECN).

    Captured as a rider inside ``market.ingest_daily_bars``. Schwab-only
    symbology — without Schwab no rows are written and A/D signals stay None.
    """

    date = models.DateField(unique=True)
    advn_close = models.FloatField(null=True, blank=True)
    decn_close = models.FloatField(null=True, blank=True)
    net_ad = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return f"BreadthDaily({self.date})"
```

- [ ] Generate the migration and verify the gate:

```bash
docker compose exec web python manage.py makemigrations market
# EXPECTED: Migrations for 'market': ... 0010_... - Create model BreadthDaily
#           - Create model IVDaily - Create model ShortInterestRecord
#           - Add field sentiment to newsitem (+ constraints/indexes)
docker compose exec web python manage.py migrate market
# EXPECTED: Applying market.0010_... OK
make check-migrations
# EXPECTED: exit 0 (no missing migrations)
```

- [ ] Run the tests — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signal_history_models.py -v
# EXPECTED: 5 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/models.py backend/apps/market/migrations/ backend/apps/market/tests/test_signal_history_models.py
git commit -m "feat(market): IVDaily, ShortInterestRecord, BreadthDaily models + NewsItem.sentiment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Retention knobs + prune entries for the three new tables

**Files:**
- Modify: `backend/config/settings/base.py` (retention block, after line 280 `AI_RETENTION_BOOK_DAYS`)
- Modify: `backend/apps/core/models.py` (`SystemSettings` retention fields, after line 30 `retention_book_days`)
- Modify: `backend/apps/core/runtime_config.py` (`_SPEC` list line 16-32 + `RuntimeConfig` dataclass line 40-56)
- Modify: `backend/apps/core/tasks.py` (`prune_retention`, imports at line 56 + `_prune` calls after line 114 + docstring model list line 30-47)
- Create: `backend/apps/core/migrations/0004_*.py` (generated)
- Test: `backend/apps/core/tests/test_prune_retention_signal_history.py`

**Interfaces:**
- Consumes: Task 1 models `apps.market.models.IVDaily` (field `date: DateField`), `ShortInterestRecord` (`settlement_date: DateField`), `BreadthDaily` (`date: DateField`).
- Produces: `runtime_config().retention_iv_days` (int, default 430), `.retention_short_interest_days` (int, default 430), `.retention_breadth_days` (int, default 800) — resolved `SystemSettings.<field> ?? settings.AI_RETENTION_*`; `core.prune_retention` result dict gains keys `"iv"`, `"short_interest"`, `"breadth"`. `EDITABLE_FIELDS` picks the three up automatically (derived from `_SPEC`), so `PATCH /api/settings/` works with the existing `retention_` floor guard (`apps/core/views.py:201-206`) — no view change needed.

**Steps:**

- [ ] Write the failing test `backend/apps/core/tests/test_prune_retention_signal_history.py`:

```python
"""prune_retention covers the signal input-history tables (IVDaily,
ShortInterestRecord, BreadthDaily) with runtime-tunable windows."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.runtime_config import EDITABLE_FIELDS, runtime_config
from apps.core.tasks import prune_retention
from apps.market.models import BreadthDaily, IVDaily, ShortInterestRecord

_NOW = timezone.now


def _iv(days_ago: int, ticker: str = "AAPL") -> IVDaily:
    return IVDaily.objects.create(
        ticker=ticker, date=(_NOW() - timedelta(days=days_ago)).date(), atm_iv=25.0
    )


def _si(days_ago: int, ticker: str = "GME") -> ShortInterestRecord:
    return ShortInterestRecord.objects.create(
        ticker=ticker, settlement_date=(_NOW() - timedelta(days=days_ago)).date()
    )


def _breadth(days_ago: int) -> BreadthDaily:
    return BreadthDaily.objects.create(
        date=(_NOW() - timedelta(days=days_ago)).date(), net_ad=100.0
    )


@pytest.mark.django_db
def test_defaults_resolve():
    rc = runtime_config()
    assert rc.retention_iv_days == 430
    assert rc.retention_short_interest_days == 430
    assert rc.retention_breadth_days == 800


def test_knobs_are_ui_editable():
    assert EDITABLE_FIELDS["retention_iv_days"] is int
    assert EDITABLE_FIELDS["retention_short_interest_days"] is int
    assert EDITABLE_FIELDS["retention_breadth_days"] is int


@pytest.mark.django_db
def test_prunes_old_keeps_recent():
    _iv(431)
    keep_iv = _iv(10)
    _si(431)
    keep_si = _si(10)
    _breadth(801)
    keep_b = _breadth(10)

    result = prune_retention()

    assert result["iv"] == 1
    assert result["short_interest"] == 1
    assert result["breadth"] == 1
    assert list(IVDaily.objects.all()) == [keep_iv]
    assert list(ShortInterestRecord.objects.all()) == [keep_si]
    assert list(BreadthDaily.objects.all()) == [keep_b]


@pytest.mark.django_db
def test_idempotent_second_run_deletes_zero():
    _iv(431)
    prune_retention()
    result = prune_retention()
    assert result["iv"] == 0
    assert result["short_interest"] == 0
    assert result["breadth"] == 0
```

- [ ] Run it — expect failures on the missing knobs:

```bash
docker compose exec web pytest apps/core/tests/test_prune_retention_signal_history.py -v
# EXPECTED: AttributeError: 'RuntimeConfig' object has no attribute 'retention_iv_days'
#           (and KeyError on EDITABLE_FIELDS / KeyError 'iv' on the prune tests)
```

- [ ] In `backend/config/settings/base.py`, extend the retention block — after line 280 (`AI_RETENTION_BOOK_DAYS = ...`) add:

```python
# Signal input-history tables (IVDaily / ShortInterestRecord / BreadthDaily).
# 430d ≈ a full 252-session IV-rank window + slack; breadth rows are tiny, keep ~800d.
AI_RETENTION_IV_DAYS = env.int("AI_RETENTION_IV_DAYS", default=430)
AI_RETENTION_SHORT_INTEREST_DAYS = env.int("AI_RETENTION_SHORT_INTEREST_DAYS", default=430)
AI_RETENTION_BREADTH_DAYS = env.int("AI_RETENTION_BREADTH_DAYS", default=800)
```

- [ ] In `backend/apps/core/models.py`, add three fields to `SystemSettings` directly after `retention_book_days = models.IntegerField(null=True, blank=True)` (line 30):

```python
    retention_iv_days = models.IntegerField(null=True, blank=True)
    retention_short_interest_days = models.IntegerField(null=True, blank=True)
    retention_breadth_days = models.IntegerField(null=True, blank=True)
```

- [ ] In `backend/apps/core/runtime_config.py`, extend `_SPEC` — after the `retention_book_days` tuple (line 23) insert:

```python
    ("retention_iv_days", "AI_RETENTION_IV_DAYS", 430),
    ("retention_short_interest_days", "AI_RETENTION_SHORT_INTEREST_DAYS", 430),
    ("retention_breadth_days", "AI_RETENTION_BREADTH_DAYS", 800),
```

  and extend the `RuntimeConfig` dataclass — after `retention_book_days: int` (line 48) insert:

```python
    retention_iv_days: int
    retention_short_interest_days: int
    retention_breadth_days: int
```

- [ ] In `backend/apps/core/tasks.py`, wire the prune entries. Change the import line 56 from:

```python
    from apps.market.models import OHLCBar, OptionChainSnapshot
```

  to:

```python
    from apps.market.models import (
        BreadthDaily,
        IVDaily,
        OHLCBar,
        OptionChainSnapshot,
        ShortInterestRecord,
    )
```

  After the `"book"` `_prune(...)` call (line 110-114), before `return results`, add (note `c.date()` — these models key on `DateField`, the shared cutoff is a datetime):

```python
    _prune(
        "iv",
        lambda c: IVDaily.objects.filter(date__lt=c.date()),
        rc.retention_iv_days,
    )
    _prune(
        "short_interest",
        lambda c: ShortInterestRecord.objects.filter(settlement_date__lt=c.date()),
        rc.retention_short_interest_days,
    )
    _prune(
        "breadth",
        lambda c: BreadthDaily.objects.filter(date__lt=c.date()),
        rc.retention_breadth_days,
    )
```

  In the docstring "Models pruned" list (after the `BookSnapshot` line, line 39), add:

```
    * IVDaily        — keep AI_RETENTION_IV_DAYS             (default 430d)
    * ShortInterestRecord — keep AI_RETENTION_SHORT_INTEREST_DAYS (default 430d)
    * BreadthDaily   — keep AI_RETENTION_BREADTH_DAYS        (default 800d)
```

- [ ] Generate the core migration and run the tests:

```bash
docker compose exec web python manage.py makemigrations core
# EXPECTED: 0004_systemsettings_retention_breadth_days_and_more.py
docker compose exec web python manage.py migrate core
make check-migrations
# EXPECTED: exit 0
docker compose exec web pytest apps/core/tests/test_prune_retention_signal_history.py apps/core/tests/test_prune_retention.py apps/core/tests/test_system_settings.py -v
# EXPECTED: all passed (new file 5 passed; existing prune/system-settings suites stay green)
```

- [ ] Commit:

```bash
git add backend/config/settings/base.py backend/apps/core/models.py backend/apps/core/runtime_config.py backend/apps/core/tasks.py backend/apps/core/migrations/ backend/apps/core/tests/test_prune_retention_signal_history.py
git commit -m "feat(core): retention knobs + prune entries for IVDaily/ShortInterestRecord/BreadthDaily

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Indicator primitives — macd_hist, adx, zscore, pct_b, hv

**Files:**
- Modify: `backend/apps/market/services/indicator.py` (append module-level functions; keep the existing `compute()` dispatcher at line 10 untouched)
- Test: `backend/apps/market/tests/test_indicator_primitives.py`

**Interfaces:**
- Consumes: existing private helpers `_sma`/`_ema` in the same module (line 23-36).
- Produces (contract-pinned signatures — later tasks and P3 call these exactly):
  ```python
  def macd_hist(closes: list[float], *, fast: int = 12, slow: int = 26, signal: int = 9) -> float | None
  def adx(bars: list[dict], *, period: int = 14) -> float | None      # bars: [{"high","low","close"},...]
  def zscore(closes: list[float], *, period: int = 20) -> float | None
  def pct_b(closes: list[float], *, period: int = 20, num_std: float = 2.0) -> float | None
  def hv(closes: list[float], *, period: int = 20) -> float | None    # annualized %, log returns
  ```
  Semantics: `zscore` uses population std over the trailing `period` closes, `None` when std==0 or short input. `pct_b` = (last close − lower band) / (upper − lower), bands = SMA ± num_std·σ (identity `pct_b == 0.5 + zscore/(2·num_std)` holds). `hv` needs `period + 1` closes, all > 0, returns σ(log returns)·√252·100 ≥ 0. `macd_hist` needs `len(closes) ≥ slow + signal` and `fast < slow`. `adx` (Wilder) needs `len(bars) ≥ 2·period + 1`, returns a value in [0, 100].

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_indicator_primitives.py`:

```python
"""Unit + property tests for the module-level indicator primitives
(macd_hist, adx, zscore, pct_b, hv) in apps.market.services.indicator."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.market.services import indicator

_UP = [float(100 + i) for i in range(60)]  # strictly rising closes
_FLAT = [100.0] * 60

_CLOSES = st.lists(
    st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=60,
)


# --- length gates: every primitive is None on short input -------------------


@pytest.mark.parametrize(
    ("fn", "arg"),
    [
        (lambda c: indicator.macd_hist(c), _UP[:34]),  # needs slow+signal = 35
        (lambda c: indicator.zscore(c), _UP[:19]),  # needs period = 20
        (lambda c: indicator.pct_b(c), _UP[:19]),
        (lambda c: indicator.hv(c), _UP[:20]),  # needs period+1 = 21
    ],
)
def test_close_primitives_none_on_short_input(fn, arg):
    assert fn(arg) is None


def test_adx_none_on_short_input():
    bars = [{"high": 101.0, "low": 99.0, "close": 100.0}] * 28  # needs 2*14+1 = 29
    assert indicator.adx(bars) is None


# --- deterministic values ----------------------------------------------------


def test_zscore_flat_series_is_none():
    assert indicator.zscore(_FLAT) is None  # std == 0 → None, never invented


def test_pct_b_flat_series_is_none():
    assert indicator.pct_b(_FLAT) is None


def test_hv_flat_series_is_zero():
    assert indicator.hv(_FLAT) == pytest.approx(0.0)


def test_macd_hist_flat_series_is_zero():
    assert indicator.macd_hist(_FLAT) == pytest.approx(0.0)


def test_macd_hist_rejects_fast_ge_slow():
    assert indicator.macd_hist(_UP, fast=26, slow=12) is None


def test_zscore_rising_series_is_positive():
    z = indicator.zscore(_UP)
    assert z is not None and z > 0


def test_pct_b_rising_series_above_half():
    b = indicator.pct_b(_UP)
    assert b is not None and b > 0.5


def test_adx_trending_series_in_range():
    bars = [{"high": 100.0 + i + 1.0, "low": 100.0 + i - 1.0, "close": 100.0 + i} for i in range(60)]
    a = indicator.adx(bars)
    assert a is not None
    assert 0.0 <= a <= 100.0
    assert a > 20.0  # a clean monotonic trend reads as trending


def test_hv_known_alternation():
    # closes alternating 100/110: log returns alternate ±log(1.1); population σ = log(1.1)
    closes = [100.0 if i % 2 == 0 else 110.0 for i in range(21)]
    expected = math.log(1.1) * math.sqrt(252.0) * 100.0
    assert indicator.hv(closes) == pytest.approx(expected, rel=1e-9)


def test_hv_none_on_non_positive_close():
    closes = [100.0] * 20 + [0.0]
    assert indicator.hv(closes) is None


# --- Hypothesis bounds (spec §10) ---------------------------------------------


@given(closes=_CLOSES)
def test_zscore_bounded_or_none(closes):
    z = indicator.zscore(closes, period=20)
    # For a point inside its own sample of n, |z| <= sqrt(n-1) with population std.
    assert z is None or abs(z) <= math.sqrt(19) + 1e-6


@given(closes=_CLOSES)
def test_pct_b_matches_zscore_identity(closes):
    z = indicator.zscore(closes, period=20)
    b = indicator.pct_b(closes, period=20, num_std=2.0)
    if z is None:
        assert b is None
    else:
        assert b == pytest.approx(0.5 + z / 4.0, abs=1e-9)


@given(
    closes=st.lists(
        st.floats(min_value=0.01, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=21,
        max_size=60,
    )
)
def test_hv_non_negative(closes):
    v = indicator.hv(closes, period=20)
    assert v is None or v >= 0.0
```

- [ ] Run it — expect AttributeError:

```bash
docker compose exec web pytest apps/market/tests/test_indicator_primitives.py -v
# EXPECTED: AttributeError: module 'apps.market.services.indicator' has no attribute 'macd_hist'
```

- [ ] Implement. In `backend/apps/market/services/indicator.py`, add `import math` under `from __future__ import annotations` (line 7), then append at the end of the file:

```python
# ---------------------------------------------------------------------------
# Module-level primitives (engine + trigger DSL share these — single source)
# ---------------------------------------------------------------------------


def _ema_series(closes: list[float], period: int) -> list[float]:
    """EMA at every bar from index period-1 onward ([] when input is short)."""
    if len(closes) < period:
        return []
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    out = [ema]
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
        out.append(ema)
    return out


def macd_hist(
    closes: list[float], *, fast: int = 12, slow: int = 26, signal: int = 9
) -> float | None:
    """MACD histogram (MACD line − signal line) at the final bar.

    None when fast >= slow or closes are shorter than slow + signal.
    """
    if fast >= slow or len(closes) < slow + signal:
        return None
    fast_s = _ema_series(closes, fast)
    slow_s = _ema_series(closes, slow)
    offset = slow - fast  # align both series to the slow EMA's first bar
    macd_line = [f - s for f, s in zip(fast_s[offset:], slow_s, strict=True)]
    sig = _ema(macd_line, signal)
    if sig is None:
        return None
    return macd_line[-1] - sig


def adx(bars: list[dict], *, period: int = 14) -> float | None:
    """Wilder's Average Directional Index over {"high","low","close"} bars.

    None with fewer than 2*period + 1 bars; otherwise a value in [0, 100].
    """
    if len(bars) < 2 * period + 1:
        return None
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []
    for i in range(1, len(bars)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        trs.append(
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        )
    # Wilder smoothing, seeded by the first `period` sums.
    atr = sum(trs[:period])
    pdm = sum(plus_dm[:period])
    mdm = sum(minus_dm[:period])
    dxs: list[float] = []
    for i in range(period, len(trs)):
        atr = atr - atr / period + trs[i]
        pdm = pdm - pdm / period + plus_dm[i]
        mdm = mdm - mdm / period + minus_dm[i]
        if atr == 0:
            dxs.append(0.0)
            continue
        pdi = 100.0 * pdm / atr
        mdi = 100.0 * mdm / atr
        denom = pdi + mdi
        dxs.append(100.0 * abs(pdi - mdi) / denom if denom else 0.0)
    if len(dxs) < period:
        return None
    adx_val = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        adx_val = (adx_val * (period - 1) + dx) / period
    return adx_val


def zscore(closes: list[float], *, period: int = 20) -> float | None:
    """Z-score of the last close vs the trailing `period` closes (population std).

    None on short input or a flat window (std == 0) — never invented.
    """
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    var = sum((c - mean) ** 2 for c in window) / period
    std = math.sqrt(max(var, 0.0))
    if std == 0:
        return None
    return (window[-1] - mean) / std


def pct_b(closes: list[float], *, period: int = 20, num_std: float = 2.0) -> float | None:
    """Bollinger %B of the last close: (close − lower) / (upper − lower).

    Bands are SMA(period) ± num_std·σ (population). None on short input,
    flat window, or non-positive num_std. Can exceed [0, 1] at extremes.
    """
    if len(closes) < period or num_std <= 0:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    std = math.sqrt(max(sum((c - mean) ** 2 for c in window) / period, 0.0))
    if std == 0:
        return None
    lower = mean - num_std * std
    upper = mean + num_std * std
    return (window[-1] - lower) / (upper - lower)


def hv(closes: list[float], *, period: int = 20) -> float | None:
    """Annualized historical volatility in percent, from log close-to-close
    returns over the trailing `period` returns (population std, √252, ×100).

    None on short input (< period + 1 closes) or any non-positive close.
    """
    if len(closes) < period + 1:
        return None
    window = closes[-(period + 1) :]
    rets: list[float] = []
    for prev, curr in zip(window, window[1:], strict=False):
        if prev <= 0 or curr <= 0:
            return None
        rets.append(math.log(curr / prev))
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return math.sqrt(max(var, 0.0)) * math.sqrt(252.0) * 100.0
```

- [ ] Run — expect PASS (and the pre-existing indicator suite stays green):

```bash
docker compose exec web pytest apps/market/tests/test_indicator_primitives.py apps/market/tests/test_indicators.py -v
# EXPECTED: all passed (new file: 17 passed)
```

- [ ] Commit:

```bash
git add backend/apps/market/services/indicator.py backend/apps/market/tests/test_indicator_primitives.py
git commit -m "feat(market): macd_hist/adx/zscore/pct_b/hv indicator primitives

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Fallback bar-depth fixes — bars→calendar-days conversion + Polygon limit parameterization

**Files:**
- Modify: `backend/apps/market/services/fallback.py` (`alt_bars`, lines 44-69; add `import math` after line 19)
- Modify: `backend/apps/market/services/polygon.py` (`fetch_daily_bars`, line 130-170; module docstring line 4)
- Test: extend `backend/apps/market/tests/test_fallback.py` and `backend/apps/market/tests/test_polygon.py`

**Interfaces:**
- Consumes: `tiingo.fetch_daily_bars(ticker, *, days=120)` and `polygon.fetch_daily_bars(ticker, *, days=120)` — both take CALENDAR days (Tiingo `startDate`, Polygon from/to range); `alt_bars(ticker, timeframe, *, limit=60)` receives a BAR count from `fetch_ohlc` (`ohlc.py:56`).
- Produces: `alt_bars` converts `limit` bars → `math.ceil(limit * 1.5)` calendar days for the tiingo/polygon branches (Alpaca/TwelveData keep the raw count — they are count-based). `polygon.fetch_daily_bars` request param `limit` equals `max(days, 1)` (no hardcoded 120), so a deep request is no longer silently truncated. Task 10's `bars=300` ingest depends on this: 300 bars → 450 calendar days.

**Steps:**

- [ ] Add the failing tests. Append to `backend/apps/market/tests/test_fallback.py`:

```python
# --- alt_bars bar-count -> calendar-day conversion ---------------------------


@pytest.mark.django_db
def test_alt_bars_tiingo_converts_bars_to_calendar_days():
    """Tiingo's `days` param is CALENDAR days; `limit` is a BAR count. A 300-bar
    request must ask for ceil(300 * 1.5) = 450 calendar days, else ~1/3 of the
    trading history silently never arrives."""
    _cred("tiingo")
    with patch("apps.market.services.tiingo.fetch_daily_bars", return_value=[{"close": 1}]) as m:
        assert fallback.alt_bars("AAPL", "1d", limit=300) == [{"close": 1}]
    m.assert_called_once_with("AAPL", days=450)


@pytest.mark.django_db
def test_alt_bars_polygon_converts_bars_to_calendar_days():
    _cred("polygon")
    with patch("apps.market.services.polygon.fetch_daily_bars", return_value=[{"close": 1}]) as m:
        assert fallback.alt_bars("AAPL", "1d", limit=300) == [{"close": 1}]
    m.assert_called_once_with("AAPL", days=450)


@pytest.mark.django_db
def test_alt_bars_alpaca_keeps_raw_bar_count():
    """Alpaca's `limit` IS a bar count — no conversion."""
    _cred("alpaca")
    with patch("apps.market.services.alpaca.fetch_bars", return_value=[]) as m:
        fallback.alt_bars("AAPL", "1d", limit=300)
    m.assert_called_once_with("AAPL", timeframe="1d", limit=300)
```

  Append to `backend/apps/market/tests/test_polygon.py`:

```python
# ---------------------------------------------------------------------------
# limit parameterization — a deep request must not be capped at 120
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_fetch_daily_bars_limit_follows_days():
    captured: dict = {}

    def _capture_get(path, params, api_key):
        captured["params"] = params
        return _RAW_AGGS_BODY

    with (
        patch("apps.market.services.polygon._api_key", return_value="k"),
        patch("apps.market.services.polygon._get", side_effect=_capture_get),
        patch(
            "apps.market.services.polygon.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        polygon_mod.fetch_daily_bars("AAPL", days=450)

    assert captured["params"]["limit"] == 450
```

- [ ] Run — expect failures:

```bash
docker compose exec web pytest apps/market/tests/test_fallback.py -k "calendar_days or raw_bar_count" apps/market/tests/test_polygon.py::test_fetch_daily_bars_limit_follows_days -v
# EXPECTED: tiingo/polygon tests FAIL — called with days=300, not days=450;
#           polygon limit test FAILS — params["limit"] == 120
```

- [ ] Implement `fallback.py`. Add `import math` directly above `from apps.secrets.models import ApiCredential` (line 21). Replace the tiingo/polygon branches of `alt_bars` (lines 61-68):

```python
    if timeframe == "1d" and _has("tiingo"):
        from apps.market.services import tiingo

        # Tiingo/Polygon take CALENDAR days; `limit` is a BAR count. ~252 trading
        # sessions per 365 calendar days -> 1.5x covers weekends + holidays.
        return tiingo.fetch_daily_bars(ticker, days=math.ceil(limit * 1.5))
    if timeframe == "1d" and _has("polygon"):
        from apps.market.services import polygon

        return polygon.fetch_daily_bars(ticker, days=math.ceil(limit * 1.5))
```

- [ ] Implement `polygon.py`. In `fetch_daily_bars` replace line 155:

```python
    params = {"adjusted": "false", "sort": "asc", "limit": 120}
```

  with:

```python
    params = {"adjusted": "false", "sort": "asc", "limit": max(days, 1)}
```

  and update the module docstring line 4 from `— daily aggregates, up to 120 bars` to `— daily aggregates over the requested day range`.

- [ ] Run — expect PASS (whole fallback + polygon suites):

```bash
docker compose exec web pytest apps/market/tests/test_fallback.py apps/market/tests/test_polygon.py -v
# EXPECTED: all passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/fallback.py backend/apps/market/services/polygon.py backend/apps/market/tests/test_fallback.py backend/apps/market/tests/test_polygon.py
git commit -m "fix(market): alt_bars converts bar counts to calendar days; parameterize polygon limit

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: FINRA keyless short-interest client

**Files:**
- Create: `backend/apps/market/services/finra.py`
- Modify: `backend/apps/market/cache.py` (`_TTL` dict, line 15-33 — add `"short_interest"`)
- Test: `backend/apps/market/tests/test_finra.py`

**Interfaces:**
- Consumes: `apps.market.cache.get_or_fetch` / `ttl_for_kind`; `apps.market.services.safe_log.safe_err`; `apps.core.mocks.is_mock_mode` (import as `from apps.core.mocks import is_mock_mode` inside the function — the sibling-provider convention).
- Produces (contract-pinned):
  ```python
  # apps/market/services/finra.py — keyless; never raises
  def fetch_short_interest(ticker: str, *, limit: int = 6) -> list[dict]
  # newest-first: [{"settlement_date": "YYYY-MM-DD", "shares_short": int|None,
  #                 "avg_daily_volume": int|None, "days_to_cover": float|None}]
  ```
  Cache kind `"short_interest"` = 21600s. Task 10's `market.refresh_short_interest` consumes this; Task 6 adds the catalog entry + probe.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_finra.py`:

```python
"""FINRA keyless short-interest client (fetch_short_interest)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services import finra

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}

_RAW_ROWS = [
    {
        "issueSymbolIdentifier": "GME",
        "settlementDate": "2026-06-15",
        "currentShortPositionQuantity": 20000000,
        "averageDailyVolumeQuantity": 4000000,
        "daysToCoverQuantity": 5.0,
    },
    {
        "issueSymbolIdentifier": "GME",
        "settlementDate": "2026-06-30",
        "currentShortPositionQuantity": 25000000,
        "averageDailyVolumeQuantity": 5000000,
        "daysToCoverQuantity": 5.0,
    },
    {"noSettlementDate": True},  # malformed row — skipped, not fatal
]


def test_mock_mode_returns_canned_rows():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        rows = finra.fetch_short_interest("GME")
    assert len(rows) == 2
    assert rows[0]["settlement_date"] == "2026-06-30"
    assert {"settlement_date", "shares_short", "avg_daily_volume", "days_to_cover"} <= set(rows[0])


def test_normalizes_and_sorts_newest_first():
    with (
        patch("apps.market.services.finra._post", return_value=_RAW_ROWS),
        patch("apps.market.services.finra.cache.get_or_fetch", **_PASSTHRU),
    ):
        rows = finra.fetch_short_interest("gme")

    assert [r["settlement_date"] for r in rows] == ["2026-06-30", "2026-06-15"]
    assert rows[0]["shares_short"] == 25_000_000
    assert rows[0]["avg_daily_volume"] == 5_000_000
    assert rows[0]["days_to_cover"] == pytest.approx(5.0)


def test_never_raises_on_network_error():
    with (
        patch("apps.market.services.finra._post", side_effect=RuntimeError("boom")),
        patch("apps.market.services.finra.cache.get_or_fetch", **_PASSTHRU),
    ):
        assert finra.fetch_short_interest("GME") == []


def test_non_list_body_yields_empty():
    with (
        patch("apps.market.services.finra._post", return_value=[]),
        patch("apps.market.services.finra.cache.get_or_fetch", **_PASSTHRU),
    ):
        assert finra.fetch_short_interest("GME") == []


def test_short_interest_ttl_registered():
    """Unregistered cache kinds silently default to 30s and hammer the API."""
    from apps.market.cache import _TTL

    assert _TTL["short_interest"] == 21600
```

- [ ] Run — expect ImportError:

```bash
docker compose exec web pytest apps/market/tests/test_finra.py -v
# EXPECTED: ImportError: cannot import name 'finra' from 'apps.market.services'
```

- [ ] Register the cache kind. In `backend/apps/market/cache.py`, add to `_TTL` after `"corporate_actions": 86400,` (line 32):

```python
    "short_interest": 21600,
```

- [ ] Create `backend/apps/market/services/finra.py`:

```python
"""FINRA consolidated equity short interest. No API key required.

Sourced from the FINRA Query API (public dataset, no auth):
- POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest

FINRA publishes short interest ~twice monthly (mid- and end-of-month settlement
dates). Cached at short_interest TTL (6h). Never raises — returns [] on any
failure. Keyless, but follows the provider template: is_mock_mode() canned
fixture, safe_err logging.
"""

from __future__ import annotations

import logging

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.services.safe_log import safe_err

log = logging.getLogger(__name__)

FINRA_BASE = "https://api.finra.org"
_DATASET_PATH = "/data/group/otcMarket/name/consolidatedShortInterest"


def _post(path: str, body: dict) -> list[dict]:
    resp = requests.post(
        f"{FINRA_BASE}{path}",
        json=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    parsed = resp.json()
    return parsed if isinstance(parsed, list) else []


def _canned_short_interest(ticker: str) -> list[dict]:
    """Deterministic fixture for MOCK_EXTERNAL / e2e mode (newest first)."""
    return [
        {
            "settlement_date": "2026-06-30",
            "shares_short": 25_000_000,
            "avg_daily_volume": 5_000_000,
            "days_to_cover": 5.0,
        },
        {
            "settlement_date": "2026-06-15",
            "shares_short": 20_000_000,
            "avg_daily_volume": 4_000_000,
            "days_to_cover": 5.0,
        },
    ]


def _int_or_none(v: object) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(v: object) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _normalize_row(raw: dict) -> dict | None:
    """Map one FINRA dataset row to the short-interest contract, or None to skip."""
    settlement = raw.get("settlementDate")
    if not settlement:
        return None
    return {
        "settlement_date": str(settlement)[:10],
        "shares_short": _int_or_none(raw.get("currentShortPositionQuantity")),
        "avg_daily_volume": _int_or_none(raw.get("averageDailyVolumeQuantity")),
        "days_to_cover": _float_or_none(raw.get("daysToCoverQuantity")),
    }


def fetch_short_interest(ticker: str, *, limit: int = 6) -> list[dict]:
    """Latest short-interest reports for `ticker`, newest-first.

    Returns [] on any network/parse failure (never raises). In mock mode
    returns a deterministic canned list.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()
    if is_mock_mode():
        return _canned_short_interest(ticker)

    body = {
        "limit": limit,
        "compareFilters": [
            {
                "compareType": "EQUAL",
                "fieldName": "issueSymbolIdentifier",
                "fieldValue": ticker,
            }
        ],
        "sortFields": ["-settlementDate"],
    }
    try:
        raw_rows = cache.get_or_fetch(
            f"market:finra:short_interest:{ticker}",
            ttl_seconds=cache.ttl_for_kind("short_interest"),
            fetcher=lambda: _post(_DATASET_PATH, body),
        )
    except Exception as exc:
        log.warning("market.finra.fetch_short_interest ticker=%s: %s", ticker, safe_err(exc))
        return []

    rows: list[dict] = []
    for raw in raw_rows if isinstance(raw_rows, list) else []:
        normalized = _normalize_row(raw) if isinstance(raw, dict) else None
        if normalized is not None:
            rows.append(normalized)
    rows.sort(key=lambda r: r["settlement_date"], reverse=True)
    return rows
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_finra.py -v
# EXPECTED: 5 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/finra.py backend/apps/market/cache.py backend/apps/market/tests/test_finra.py
git commit -m "feat(market): keyless FINRA short-interest client

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: FINRA data-source catalog entry + settings-Test probe (keyless probe wiring)

**Files:**
- Modify: `backend/apps/secrets/data_sources.py` (append entry to `DATA_SOURCES`, before the `edgar` entry at line 101)
- Modify: `backend/apps/secrets/data_source_test.py` (add `_probe_finra`, register in `_PROBES` line 103-112, add `supports_test()`, make `test_credential` keyless-aware, line 123-141)
- Modify: `backend/apps/secrets/views.py` (import line 24; `data_source_test` guard line 377-378)
- Test: `backend/apps/secrets/tests/test_finra_data_source.py`

**Interfaces:**
- Consumes: `get_data_source(provider)` (`data_sources.py:124`); the existing status-code `_classify` (`data_source_test.py:115`).
- Produces: catalog entry `{"provider": "finra", "auth": "none", ...}` (keyless → `GET /api/schwab/data-sources/` reports `configured: true` automatically via `views.py:306-307`); `supports_test(provider) -> bool`; `POST /api/schwab/data-sources/finra/test/` now reaches `_probe_finra` (today the view 400s every `auth == "none"` source — the guard is relaxed ONLY for keyless sources that have a probe, so edgar/treasury keep their current 400).

**Steps:**

- [ ] Write the failing test `backend/apps/secrets/tests/test_finra_data_source.py`:

```python
"""FINRA catalog entry + keyless Test-button probe wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.secrets import data_source_test as probe_mod
from apps.secrets.data_source_test import supports_test, test_credential
from apps.secrets.data_sources import get_data_source

# NOTE: _PROBES holds function REFERENCES captured at module load — patching the
# _probe_finra module attribute would not affect the dict. Patch the dict entry
# (patch.dict), the same convention test_data_sources.py uses.


def test_catalog_entry_is_keyless():
    ds = get_data_source("finra")
    assert ds is not None
    assert ds["auth"] == "none"
    assert ds["fields"] == []


def test_supports_test_finra_but_not_other_keyless():
    assert supports_test("finra") is True
    assert supports_test("edgar") is False
    assert supports_test("treasury") is False


@pytest.mark.django_db
def test_keyless_probe_runs_without_credential_row():
    """A keyless source must not require an ApiCredential row to probe."""
    with (
        patch("apps.core.mocks.is_mock_mode", return_value=False),
        patch.dict(probe_mod._PROBES, {"finra": lambda _t: SimpleNamespace(status_code=200)}),
    ):
        result = test_credential("finra")
    assert result == {"ok": True, "message": "Key works."}


@pytest.mark.django_db
def test_keyed_provider_still_requires_credential_row():
    with patch("apps.core.mocks.is_mock_mode", return_value=False):
        result = test_credential("polygon")
    assert result == {"ok": False, "message": "No credential saved yet."}


@pytest.mark.django_db
def test_endpoint_allows_finra_but_still_rejects_edgar(client):
    with (
        patch("apps.core.mocks.is_mock_mode", return_value=False),
        patch.dict(probe_mod._PROBES, {"finra": lambda _t: SimpleNamespace(status_code=200)}),
    ):
        ok = client.post("/api/schwab/data-sources/finra/test/")
        rejected = client.post("/api/schwab/data-sources/edgar/test/")
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert rejected.status_code == 400


@pytest.mark.django_db
def test_list_endpoint_reports_finra_configured(client):
    body = client.get("/api/schwab/data-sources/").json()
    entry = next(ds for ds in body["data_sources"] if ds["provider"] == "finra")
    assert entry["status"]["configured"] is True
```

- [ ] Run — expect ImportError / failures:

```bash
docker compose exec web pytest apps/secrets/tests/test_finra_data_source.py -v
# EXPECTED: ImportError: cannot import name 'supports_test' from 'apps.secrets.data_source_test'
```

- [ ] In `backend/apps/secrets/data_sources.py`, insert into `DATA_SOURCES` between the `marketaux` entry (ends line 100) and the `edgar` entry (line 101):

```python
    {
        "provider": "finra",
        "label": "FINRA",
        "auth": "none",
        "fields": [],
        "blurb": "Consolidated equity short interest, published twice monthly. No key required.",
        "signup_url": "",
        "docs_url": "https://developer.finra.org/docs",
    },
```

- [ ] In `backend/apps/secrets/data_source_test.py`, add the probe after `_probe_marketaux` (line 100):

```python
def _probe_finra(t: dict):
    # Keyless — probes reachability of the public short-interest dataset.
    return requests.post(
        "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest",
        json={"limit": 1},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=_TIMEOUT,
    )
```

  register it in `_PROBES` (after `"marketaux": _probe_marketaux,`):

```python
    "finra": _probe_finra,
```

  add below the `_PROBES` dict:

```python
def supports_test(provider: str) -> bool:
    """Whether a probe exists for `provider` — drives the keyless Test button."""
    return provider in _PROBES
```

  and replace the body of `test_credential` (lines 123-141) with a keyless-aware version:

```python
def test_credential(provider: str) -> dict:
    """Validate the saved credential for ``provider`` with a minimal probe. Never raises.

    Keyless sources (auth == "none") probe with an empty token and skip the
    ApiCredential lookup — there is nothing stored to load.
    """
    from apps.core.mocks import is_mock_mode

    from apps.secrets.data_sources import get_data_source

    if is_mock_mode():
        return {"ok": True, "message": "Mock mode — credential not contacted."}
    probe = _PROBES.get(provider)
    if probe is None:
        return {"ok": False, "message": "Testing isn't supported for this source."}
    token: dict = {}
    if (get_data_source(provider) or {}).get("auth") != "none":
        try:
            cred = ApiCredential.objects.get(provider=provider)
        except ApiCredential.DoesNotExist:
            return {"ok": False, "message": "No credential saved yet."}
        token = cred.token or {}
    try:
        resp = probe(token)
    except Exception as exc:
        log.warning("market.data_source_test.failed provider=%s: %s", provider, safe_err(exc))
        return {"ok": False, "message": "Couldn't reach the provider."}
    return _classify(resp)
```

- [ ] In `backend/apps/secrets/views.py`, change the import at line 24 from:

```python
from apps.secrets.data_source_test import test_credential
```

  to:

```python
from apps.secrets.data_source_test import supports_test, test_credential
```

  and in `data_source_test` (line 377-378) replace:

```python
    if ds["auth"] in ("none", "oauth"):
        return _ds_err("not_key_managed", f"{ds['label']} has no key to test.", 400)
```

  with:

```python
    if ds["auth"] == "oauth" or (ds["auth"] == "none" and not supports_test(provider)):
        return _ds_err("not_key_managed", f"{ds['label']} has no key to test.", 400)
```

- [ ] Run — expect PASS, plus the existing data-source suites stay green:

```bash
docker compose exec web pytest apps/secrets/tests/test_finra_data_source.py apps/secrets/tests/test_data_sources.py apps/market/tests/test_data_source_endpoints.py -v
# EXPECTED: all passed
```

- [ ] Commit:

```bash
git add backend/apps/secrets/data_sources.py backend/apps/secrets/data_source_test.py backend/apps/secrets/views.py backend/apps/secrets/tests/test_finra_data_source.py
git commit -m "feat(secrets): FINRA data-source catalog entry + keyless Test probe

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Finnhub free-tier fetchers — fetch_insider_transactions + fetch_recommendations

**Files:**
- Modify: `backend/apps/market/services/fundamentals.py` (imports line 14; add `_finnhub_get_list` after `_finnhub_get` line 30-35; append fetchers + canned fixtures at end of file)
- Test: `backend/apps/market/tests/test_fundamentals_insider_recs.py`

**Interfaces:**
- Consumes: existing `_finnhub_api_key()` (line 26), `_finnhub_get(path, params, api_key)` (line 30), `cache.get_or_fetch` + `ttl_for_kind("fundamentals")` (86400s — the 24h cache the spec asks for; no new cache kind).
- Produces (contract-pinned):
  ```python
  def fetch_insider_transactions(ticker: str) -> dict   # {"net_90d": float|None, "buys": int, "sells": int}; {} on failure
  def fetch_recommendations(ticker: str) -> list[dict]  # Finnhub monthly rows, newest first; [] on failure
  # recommendation row shape (Finnhub verbatim):
  # {"period": "YYYY-MM-DD", "strongBuy": int, "buy": int, "hold": int, "sell": int, "strongSell": int}
  ```
  Task 16 (positioning family) consumes both. Neither persists anything — the recommendation endpoint returns its own monthly history (spec §5.4).

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_fundamentals_insider_recs.py`:

```python
"""Finnhub insider-transactions + analyst-recommendations fetchers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services import fundamentals

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}

_RAW_INSIDER = {
    "data": [
        {"change": 10_000, "transactionDate": "2026-06-20"},
        {"change": -4_000, "transactionDate": "2026-06-10"},
        {"change": 6_000, "transactionDate": "2026-05-15"},
        {"change": "bogus"},  # malformed — skipped
    ]
}

_RAW_RECS = [
    {"period": "2026-06-01", "strongBuy": 8, "buy": 18, "hold": 10, "sell": 3, "strongSell": 1},
    {"period": "2026-07-01", "strongBuy": 10, "buy": 20, "hold": 8, "sell": 2, "strongSell": 1},
]


# --- fetch_insider_transactions ----------------------------------------------


def test_insider_nets_buys_and_sells():
    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get", return_value=_RAW_INSIDER),
        patch("apps.market.services.fundamentals.cache.get_or_fetch", **_PASSTHRU),
    ):
        out = fundamentals.fetch_insider_transactions("aapl")
    assert out == {"net_90d": pytest.approx(12_000.0), "buys": 2, "sells": 1}


def test_insider_empty_data_reports_none_not_zero():
    """No rows in 90d is 'unknown', not 'net zero' — absent, never invented."""
    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get", return_value={"data": []}),
        patch("apps.market.services.fundamentals.cache.get_or_fetch", **_PASSTHRU),
    ):
        out = fundamentals.fetch_insider_transactions("AAPL")
    assert out == {"net_90d": None, "buys": 0, "sells": 0}


def test_insider_missing_key_returns_empty_dict():
    with patch("apps.market.services.fundamentals._finnhub_api_key", return_value=None):
        assert fundamentals.fetch_insider_transactions("AAPL") == {}


def test_insider_never_raises():
    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get", side_effect=RuntimeError("boom")),
        patch("apps.market.services.fundamentals.cache.get_or_fetch", **_PASSTHRU),
    ):
        assert fundamentals.fetch_insider_transactions("AAPL") == {}


def test_insider_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        out = fundamentals.fetch_insider_transactions("AAPL")
    assert set(out) == {"net_90d", "buys", "sells"}


# --- fetch_recommendations -----------------------------------------------------


def test_recommendations_sorted_newest_first():
    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch("apps.market.services.fundamentals._finnhub_get_list", return_value=_RAW_RECS),
        patch("apps.market.services.fundamentals.cache.get_or_fetch", **_PASSTHRU),
    ):
        rows = fundamentals.fetch_recommendations("AAPL")
    assert [r["period"] for r in rows] == ["2026-07-01", "2026-06-01"]


def test_recommendations_missing_key_returns_empty_list():
    with patch("apps.market.services.fundamentals._finnhub_api_key", return_value=None):
        assert fundamentals.fetch_recommendations("AAPL") == []


def test_recommendations_never_raises():
    with (
        patch("apps.market.services.fundamentals._finnhub_api_key", return_value="k"),
        patch(
            "apps.market.services.fundamentals._finnhub_get_list",
            side_effect=RuntimeError("boom"),
        ),
        patch("apps.market.services.fundamentals.cache.get_or_fetch", **_PASSTHRU),
    ):
        assert fundamentals.fetch_recommendations("AAPL") == []


def test_recommendations_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        rows = fundamentals.fetch_recommendations("AAPL")
    assert rows and rows[0]["period"] >= rows[-1]["period"]
    assert {"strongBuy", "buy", "hold", "sell", "strongSell"} <= set(rows[0])
```

- [ ] Run — expect AttributeError:

```bash
docker compose exec web pytest apps/market/tests/test_fundamentals_insider_recs.py -v
# EXPECTED: AttributeError: module ... has no attribute 'fetch_insider_transactions'
```

- [ ] Implement in `backend/apps/market/services/fundamentals.py`. Change the datetime import (line 14) from:

```python
from datetime import UTC, datetime
```

  to:

```python
from datetime import UTC, datetime, timedelta
```

  Add after `_finnhub_get` (line 30-35):

```python
def _finnhub_get_list(path: str, params: dict, api_key: str) -> list:
    p = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=p, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else []
```

  Append at the end of the file:

```python
# ---------------------------------------------------------------------------
# Insider transactions + analyst recommendations (Finnhub free tier)
# ---------------------------------------------------------------------------


def _canned_insider(ticker: str) -> dict:
    """Deterministic fixture for MOCK_EXTERNAL / e2e mode."""
    return {"net_90d": 120_000.0, "buys": 3, "sells": 1}


def _canned_recommendations(ticker: str) -> list[dict]:
    """Deterministic fixture for MOCK_EXTERNAL / e2e mode (newest first)."""
    return [
        {"period": "2026-07-01", "strongBuy": 10, "buy": 20, "hold": 8, "sell": 2, "strongSell": 1},
        {"period": "2026-06-01", "strongBuy": 8, "buy": 18, "hold": 10, "sell": 3, "strongSell": 1},
    ]


def fetch_insider_transactions(ticker: str) -> dict:
    """Net insider share flow over the trailing 90 days, from Finnhub
    /stock/insider-transactions.

    Returns {"net_90d": float|None, "buys": int, "sells": int} — net_90d is None
    (not 0.0) when no parsable rows exist, so "no data" never reads as "flat".
    {} on missing key or fetch failure (never raises). Cached 24h. Not persisted.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()
    if is_mock_mode():
        return _canned_insider(ticker)

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("market.fundamentals: no credential configured, skipping insider fetch")
        return {}

    from_date = (datetime.now(UTC).date() - timedelta(days=90)).isoformat()
    try:
        body = cache.get_or_fetch(
            f"market:fundamentals:insider:{ticker}",
            ttl_seconds=cache.ttl_for_kind("fundamentals"),
            fetcher=lambda: _finnhub_get(
                "/stock/insider-transactions", {"symbol": ticker, "from": from_date}, api_key
            ),
        )
    except Exception as exc:
        log.warning("market.fundamentals.insider_failed %s: %s", ticker, exc)
        return {}

    rows = body.get("data") or []
    net = 0.0
    buys = sells = 0
    seen_any = False
    for row in rows if isinstance(rows, list) else []:
        try:
            change = float(row.get("change"))
        except (TypeError, ValueError):
            continue
        seen_any = True
        net += change
        if change > 0:
            buys += 1
        elif change < 0:
            sells += 1
    return {"net_90d": net if seen_any else None, "buys": buys, "sells": sells}


def fetch_recommendations(ticker: str) -> list[dict]:
    """Finnhub monthly analyst recommendation rows for `ticker`, newest first.

    Row shape (Finnhub verbatim): {"period": "YYYY-MM-DD", "strongBuy": int,
    "buy": int, "hold": int, "sell": int, "strongSell": int}. [] on missing key
    or fetch failure (never raises). Cached 24h. Not persisted — the endpoint
    returns its own monthly history.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()
    if is_mock_mode():
        return _canned_recommendations(ticker)

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("market.fundamentals: no credential configured, skipping recommendations fetch")
        return []

    try:
        body = cache.get_or_fetch(
            f"market:fundamentals:recommendations:{ticker}",
            ttl_seconds=cache.ttl_for_kind("fundamentals"),
            fetcher=lambda: _finnhub_get_list("/stock/recommendation", {"symbol": ticker}, api_key),
        )
    except Exception as exc:
        log.warning("market.fundamentals.recommendations_failed %s: %s", ticker, exc)
        return []

    rows = [r for r in body if isinstance(r, dict) and r.get("period")] if isinstance(body, list) else []
    rows.sort(key=lambda r: str(r["period"]), reverse=True)
    return rows
```

- [ ] Run — expect PASS (plus the existing fundamentals suite):

```bash
docker compose exec web pytest apps/market/tests/test_fundamentals_insider_recs.py apps/market/tests/test_fundamentals_service.py -v
# EXPECTED: all passed (new file: 9 passed)
```

- [ ] Commit:

```bash
git add backend/apps/market/services/fundamentals.py backend/apps/market/tests/test_fundamentals_insider_recs.py
git commit -m "feat(market): Finnhub insider-transactions + analyst-recommendations fetchers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Persist Marketaux per-ticker sentiment into NewsItem.sentiment

**Files:**
- Modify: `backend/apps/market/services/marketaux.py` (upsert defaults line 181-192; module docstring line 7-8; `fetch_news` docstring line 122-129)
- Test: extend `backend/apps/market/tests/test_marketaux.py`

**Interfaces:**
- Consumes: Task 1's `NewsItem.sentiment` (nullable FloatField); `_normalize_item` already returns `"sentiment": {SYM: float}` per entity plus `"ticker"` = first entity symbol (line 84-103).
- Produces: each upserted `NewsItem` row carries `sentiment` = the score for the row's primary ticker (or `None` when Marketaux gave none). Task 16's `news_sentiment_7d` reads `NewsItem.objects.filter(sentiment__isnull=False)`. Finnhub/Tiingo news writers are untouched and keep writing `sentiment=NULL`.

**Steps:**

- [ ] Add the failing test. Append to `backend/apps/market/tests/test_marketaux.py` (it already imports `patch`, `pytest`, and the module — reuse its existing imports; if the file's raw-fixture names differ, add these self-contained tests at the end):

```python
# --- NewsItem.sentiment persistence -------------------------------------------

_RAW_WITH_SENTIMENT = {
    "data": [
        {
            "uuid": "sent-1",
            "title": "AAPL pops",
            "description": "d",
            "url": "https://example.com/1",
            "source": "src",
            "published_at": "2026-07-01T14:30:00Z",
            "entities": [{"symbol": "AAPL", "sentiment_score": 0.42}],
        },
        {
            "uuid": "sent-2",
            "title": "MSFT drifts",
            "description": "d",
            "url": "https://example.com/2",
            "source": "src",
            "published_at": "2026-07-01T15:00:00Z",
            "entities": [{"symbol": "MSFT"}],  # no sentiment_score
        },
    ]
}


@pytest.mark.django_db
def test_fetch_news_persists_primary_ticker_sentiment():
    from apps.market.models import NewsItem

    with (
        patch("apps.market.services.marketaux._api_key", return_value="k"),
        patch(
            "apps.market.services.marketaux.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
        patch(
            "apps.market.services.marketaux._fetch_chunk",
            return_value=_RAW_WITH_SENTIMENT["data"],
        ),
    ):
        marketaux.fetch_news(["AAPL", "MSFT"])

    with_score = NewsItem.objects.get(provider="marketaux", external_id="sent-1")
    assert with_score.sentiment == pytest.approx(0.42)

    without_score = NewsItem.objects.get(provider="marketaux", external_id="sent-2")
    assert without_score.sentiment is None
```

  NOTE: if `test_marketaux.py` refers to the module by a different alias, mirror its import line (`from apps.market.services import marketaux`) — check the top of the file before pasting.

- [ ] Run — expect failure (field never written):

```bash
docker compose exec web pytest apps/market/tests/test_marketaux.py::test_fetch_news_persists_primary_ticker_sentiment -v
# EXPECTED: FAILED — with_score.sentiment is None (upsert never sets it)
```

- [ ] Implement in `backend/apps/market/services/marketaux.py`. In the `NewsItem.objects.update_or_create` defaults dict (lines 184-191), add after `"published_at": normalized["published_at"],`:

```python
                    "sentiment": normalized["sentiment"].get(normalized["ticker"]),
```

  Update the module docstring line 7-8 from:

```
Cached news TTL. Upserts NewsItem on each real fetch (sentiment is NOT stored on the model —
it lives only in the returned dict). Never raises — returns [] on any failure.
```

  to:

```
Cached news TTL. Upserts NewsItem on each real fetch; the primary ticker's
sentiment_score is persisted to NewsItem.sentiment (None when Marketaux gives no
score). Never raises — returns [] on any failure.
```

  In the `fetch_news` docstring, replace the line `NewsItem rows. Sentiment lives only in the returned dicts (not on NewsItem).` with `NewsItem rows (persisting the primary ticker's sentiment score per row).`, and delete the stale comment line `# Upsert the NewsItem row (no sentiment field on the model)` above the upsert (line 179), replacing it with `# Upsert the NewsItem row (sentiment = the row's primary-ticker score)`. Also update the comment at line 196 `# Build the return dict (include tickers + sentiment not stored in DB)` to `# Build the return dict (full per-ticker sentiment map rides along)`.

- [ ] Run — expect PASS (whole marketaux suite):

```bash
docker compose exec web pytest apps/market/tests/test_marketaux.py -v
# EXPECTED: all passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/marketaux.py backend/apps/market/tests/test_marketaux.py
git commit -m "feat(market): persist Marketaux per-ticker sentiment to NewsItem.sentiment

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: IV summary service — summarize_chain

**Files:**
- Create: `backend/apps/market/services/iv_summary.py`
- Test: `backend/apps/market/tests/test_iv_summary.py`

**Interfaces:**
- Consumes: `apps.market.services.chain.fetch_chain(ticker)` (returns `{"underlying_last": str|None, "expiries": {date: {"calls": [...], "puts": [...]}}}`; raises `SchwabNotConnectedError` when neither Schwab nor Tradier is available); `apps.market.services.option_analytics.chain_analytics(contracts, *, spot)` (returns `{"put_call": {...}, "term_structure": [{"expiry", "atm_iv"}], "gex": {"total", "flip_strike", ...}, ...}`).
- Produces:
  ```python
  def summarize_chain(ticker: str) -> dict | None
  # {"atm_iv", "term_slope", "put_call_vol", "put_call_oi", "gex_total",
  #  "flip_strike", "spot"} — every value float|None.
  # None (not a dict) when no chain source is configured or the chain is empty. Never raises.
  ```
  `atm_iv` = front-expiry ATM IV (percent units, Schwab's `volatility` convention); `term_slope` = far ATM IV − front ATM IV (percentage points, None with <2 usable expiries). Task 10's `ingest_iv_summary` and Task 15's volatility family both consume this — the ONE chain-flattening + distillation source.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_iv_summary.py`:

```python
"""summarize_chain — distilling one chain payload into IVDaily scalars."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.services.iv_summary import summarize_chain


def _contract(strike, iv, side_fields=None):
    base = {
        "strike": f"{strike:.2f}",
        "bid": "1.00",
        "ask": "1.10",
        "last": "1.05",
        "volume": 100,
        "oi": 200,
        "delta": "0.50",
        "gamma": "0.02",
        "theta": "-0.05",
        "vega": "0.10",
        "iv": f"{iv:.2f}",
    }
    base.update(side_fields or {})
    return base


_PAYLOAD = {
    "ticker": "AAPL",
    "underlying_last": "200.00",
    "expiries": {
        "2026-07-17": {
            "calls": [_contract(200.0, 25.0), _contract(210.0, 27.0)],
            "puts": [_contract(200.0, 26.0), _contract(190.0, 28.0)],
        },
        "2026-08-21": {
            "calls": [_contract(200.0, 30.0)],
            "puts": [_contract(200.0, 31.0)],
        },
    },
}


def test_summarize_chain_scalar_shape():
    with patch("apps.market.services.chain.fetch_chain", return_value=_PAYLOAD):
        out = summarize_chain("AAPL")

    assert out is not None
    assert set(out) == {
        "atm_iv",
        "term_slope",
        "put_call_vol",
        "put_call_oi",
        "gex_total",
        "flip_strike",
        "spot",
    }
    # Front-expiry ATM (strike 200 call) IV is 25.0; far expiry is 30.0.
    assert out["atm_iv"] == pytest.approx(25.0)
    assert out["term_slope"] == pytest.approx(5.0)
    assert out["spot"] == pytest.approx(200.0)
    # Equal volume both sides in the fixture -> put/call volume ratio 1.0
    assert out["put_call_vol"] == pytest.approx(1.0)
    assert out["put_call_oi"] == pytest.approx(1.0)
    assert out["gex_total"] is not None


def test_no_chain_source_returns_none():
    with patch(
        "apps.market.services.chain.fetch_chain",
        side_effect=SchwabNotConnectedError("no schwab"),
    ):
        assert summarize_chain("AAPL") is None


def test_empty_chain_returns_none():
    with patch(
        "apps.market.services.chain.fetch_chain",
        return_value={"underlying_last": None, "expiries": {}},
    ):
        assert summarize_chain("AAPL") is None


def test_never_raises_on_any_provider_error():
    with patch("apps.market.services.chain.fetch_chain", side_effect=RuntimeError("boom")):
        assert summarize_chain("AAPL") is None
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_iv_summary.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.iv_summary'
```

- [ ] Create `backend/apps/market/services/iv_summary.py`:

```python
"""Distill one option chain into the compact IVDaily scalar set.

``summarize_chain`` fetches the (cached) chain via ``fetch_chain``, flattens it
the way expected_move does, runs ``chain_analytics``, and reduces the result to
the scalars IVDaily persists: front-expiry ATM IV, term slope (far minus front
ATM IV), put/call volume + OI ratios, dealer GEX total and flip strike.

Returns None when no chain source is available or the chain is empty — never
raises. Shared by the nightly ``market.ingest_iv_summary`` task and the
volatility signal family, so both read identical distillation math.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _flat_contracts(payload: dict) -> list[dict]:
    """OptionChainSnapshot.payload -> flat [{..., "side", "expiry"}] for chain_analytics."""
    flat: list[dict] = []
    for exp, section in ((payload or {}).get("expiries") or {}).items():
        if not isinstance(section, dict):
            continue
        for c in section.get("calls", []):
            flat.append({**c, "side": "call", "expiry": exp})
        for c in section.get("puts", []):
            flat.append({**c, "side": "put", "expiry": exp})
    return flat


def _spot_of(payload: dict) -> float | None:
    raw = (payload or {}).get("underlying_last")
    try:
        return float(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _term_scalars(term_structure: list[dict]) -> tuple[float | None, float | None]:
    """(front ATM IV, far-minus-front slope) from chain_analytics' term structure.

    Slope is None with fewer than two usable expiries — never invented.
    """
    ivs = [row["atm_iv"] for row in term_structure if row.get("atm_iv") is not None]
    if not ivs:
        return None, None
    front = ivs[0]
    slope = (ivs[-1] - front) if len(ivs) >= 2 else None
    return front, slope


def summarize_chain(ticker: str) -> dict | None:
    """Compact volatility scalars for `ticker`'s current chain, or None.

    Shape: {"atm_iv", "term_slope", "put_call_vol", "put_call_oi", "gex_total",
    "flip_strike", "spot"} — all float|None. None (not a dict) when no chain
    source is configured, the chain is empty, or the provider errors.
    """
    from apps.market.services.chain import fetch_chain
    from apps.market.services.option_analytics import chain_analytics

    try:
        payload = fetch_chain(ticker)
    except Exception as exc:
        # SchwabNotConnectedError with no Tradier fallback, or any provider
        # error: no chain source -> no summary (callers skip the ticker).
        log.info("market.iv_summary.no_chain ticker=%s: %s", ticker, exc)
        return None

    flat = _flat_contracts(payload)
    if not flat:
        return None
    spot = _spot_of(payload)
    analytics = chain_analytics(flat, spot=spot)
    atm_iv, term_slope = _term_scalars(analytics.get("term_structure") or [])
    put_call = analytics.get("put_call") or {}
    gex = analytics.get("gex") or {}
    return {
        "atm_iv": atm_iv,
        "term_slope": term_slope,
        "put_call_vol": put_call.get("volume_ratio"),
        "put_call_oi": put_call.get("oi_ratio"),
        "gex_total": gex.get("total"),
        "flip_strike": gex.get("flip_strike"),
        "spot": spot,
    }
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_iv_summary.py -v
# EXPECTED: 4 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/iv_summary.py backend/apps/market/tests/test_iv_summary.py
git commit -m "feat(market): summarize_chain distills a chain into IVDaily scalars

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Beat tasks — ingest_iv_summary + refresh_short_interest; ingest_daily_bars bars=300 + BreadthDaily rider (celery + inventory SAME commit)

**Files:**
- Modify: `backend/apps/market/tasks.py` (`ingest_daily_bars` line 109-130; append `_capture_breadth_daily` + two new tasks)
- Modify: `backend/config/celery.py` (`beat_schedule`, line 64-146 — two new entries)
- Modify: `backend/apps/core/scheduled_tasks.py` (`SCHEDULED_WORK` list — two new entries; module docstring line 3 "19 beat entries" → "21 beat entries")
- Modify: `backend/apps/core/tests/test_scheduled_work_inventory.py` (docstring line 3 only: "19 beat entries" → "21 beat entries")
- Modify: `backend/apps/market/tests/test_ingest_daily_bars.py` (bars=300 assertions)
- Test: `backend/apps/market/tests/test_ingest_iv_summary.py`, `backend/apps/market/tests/test_refresh_short_interest.py`, additions to `test_ingest_daily_bars.py`

**Interfaces:**
- Consumes: Task 1 models (`IVDaily`, `ShortInterestRecord`, `BreadthDaily`); Task 3 `indicator.hv(closes, *, period=20)`; Task 5 `finra.fetch_short_interest(ticker) -> list[dict]` (rows carry `settlement_date` "YYYY-MM-DD" strings); Task 9 `summarize_chain(ticker) -> dict | None`; existing `fetch_quotes` (`quotes.py:16`, raises `SchwabNotConnectedError` with no provider), `fetch_ohlc` (`ohlc.py:43`), `WatchlistSymbol` (already imported at `tasks.py:16`).
- Produces: Celery tasks `market.ingest_iv_summary` (daily 20:45 UTC) and `market.refresh_short_interest` (daily 10:00 UTC), both inventoried in `SCHEDULED_WORK` in the SAME commit (drift gate `test_scheduled_work_inventory.py`); `ingest_daily_bars` now requests `bars=300` and returns `{"requested", "ingested", "breadth": bool}`.
- Deploy note (goes in the commit body): worker/beat do not hot-reload task modules — `docker compose restart worker beat` after merging.

**Steps:**

- [ ] Update the existing ingest tests for bars=300. In `backend/apps/market/tests/test_ingest_daily_bars.py`, extend `test_universe_coverage_and_timeframe` — after the timeframe-assert loop (the `for c in mock_fetch.call_args_list:` block), add inside the same test:

```python
    # Deep history: 300 bars covers 252-session lookbacks (mom_12_1, IV rank inputs).
    for c in mock_fetch.call_args_list:
        assert c.kwargs.get("bars") == 300, f"Expected bars=300 but got {c.kwargs} for {c.args}"
```

  and append two new tests at the end of the file:

```python
@pytest.mark.django_db
def test_breadth_daily_row_written_when_schwab_quotes_present():
    from apps.market.models import BreadthDaily

    with (
        patch("apps.market.services.ohlc.fetch_ohlc", return_value=[]),
        patch(
            "apps.market.services.quotes.fetch_quotes",
            return_value={"$ADVN": {"last": 2100.0}, "$DECN": {"last": 900.0}},
        ),
    ):
        result = ingest_daily_bars()

    assert result["breadth"] is True
    row = BreadthDaily.objects.get()
    assert row.advn_close == 2100.0
    assert row.decn_close == 900.0
    assert row.net_ad == 1200.0

    # Idempotent: a re-run the same day updates in place, no second row.
    with (
        patch("apps.market.services.ohlc.fetch_ohlc", return_value=[]),
        patch(
            "apps.market.services.quotes.fetch_quotes",
            return_value={"$ADVN": {"last": 2200.0}, "$DECN": {"last": 800.0}},
        ),
    ):
        ingest_daily_bars()
    assert BreadthDaily.objects.count() == 1
    assert BreadthDaily.objects.get().net_ad == 1400.0


@pytest.mark.django_db
def test_no_breadth_row_without_schwab_symbols():
    """Free-quote fallbacks can't resolve $-prefixed indices — quotes come back
    without $ADVN/$DECN and NO row is written (A/D signals stay None)."""
    from apps.market.models import BreadthDaily

    with (
        patch("apps.market.services.ohlc.fetch_ohlc", return_value=[]),
        patch("apps.market.services.quotes.fetch_quotes", return_value={}),
    ):
        result = ingest_daily_bars()

    assert result["breadth"] is False
    assert BreadthDaily.objects.count() == 0
```

- [ ] Write the failing test `backend/apps/market/tests/test_ingest_iv_summary.py`:

```python
"""market.ingest_iv_summary — nightly IVDaily distillation for the watchlist."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.market.models import IVDaily
from apps.market.tasks import ingest_iv_summary
from apps.profiles.models import Watchlist, WatchlistSymbol

_SUMMARY = {
    "atm_iv": 25.0,
    "term_slope": 5.0,
    "put_call_vol": 1.1,
    "put_call_oi": 0.9,
    "gex_total": 1_000_000.0,
    "flip_strike": 195.0,
    "spot": 200.0,
}


def _watch(*tickers: str) -> None:
    wl = Watchlist.objects.create(name="Core")
    for t in tickers:
        WatchlistSymbol.objects.create(watchlist=wl, ticker=t)


@pytest.mark.django_db
def test_upserts_one_row_per_ticker_per_day():
    _watch("AAPL", "NVDA")
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=_SUMMARY):
        result = ingest_iv_summary()

    assert result["written"] == 2
    today = timezone.now().date()
    row = IVDaily.objects.get(ticker="AAPL", date=today)
    assert row.atm_iv == 25.0
    assert row.term_slope == 5.0
    assert row.gex_total == 1_000_000.0

    # Idempotent same-day re-run: update in place, no duplicates.
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=_SUMMARY):
        ingest_iv_summary()
    assert IVDaily.objects.filter(ticker="AAPL").count() == 1


@pytest.mark.django_db
def test_no_chain_source_skips_silently():
    _watch("AAPL")
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=None):
        result = ingest_iv_summary()
    assert result["written"] == 0
    assert IVDaily.objects.count() == 0


@pytest.mark.django_db
def test_never_raises_per_ticker_failure():
    _watch("AAPL", "NVDA")

    def _boom(ticker):
        if ticker == "AAPL":
            raise RuntimeError("boom")
        return _SUMMARY

    with patch("apps.market.services.iv_summary.summarize_chain", side_effect=_boom):
        result = ingest_iv_summary()
    assert result["written"] == 1
    assert IVDaily.objects.filter(ticker="NVDA").exists()
```

- [ ] Write the failing test `backend/apps/market/tests/test_refresh_short_interest.py`:

```python
"""market.refresh_short_interest — daily FINRA upsert (no-op without a new report)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from apps.market.models import ShortInterestRecord
from apps.market.tasks import refresh_short_interest
from apps.profiles.models import Watchlist, WatchlistSymbol

_ROWS = [
    {
        "settlement_date": "2026-06-30",
        "shares_short": 25_000_000,
        "avg_daily_volume": 5_000_000,
        "days_to_cover": 5.0,
    },
    {
        "settlement_date": "2026-06-15",
        "shares_short": 20_000_000,
        "avg_daily_volume": 4_000_000,
        "days_to_cover": 5.0,
    },
    {"settlement_date": "not-a-date"},  # malformed — skipped, not fatal
]


def _watch(*tickers: str) -> None:
    wl = Watchlist.objects.create(name="Core")
    for t in tickers:
        WatchlistSymbol.objects.create(watchlist=wl, ticker=t)


@pytest.mark.django_db
def test_creates_rows_then_noops_on_rerun():
    _watch("GME")
    with patch("apps.market.services.finra.fetch_short_interest", return_value=_ROWS):
        first = refresh_short_interest()
        second = refresh_short_interest()

    assert first["created"] == 2
    assert second["created"] == 0  # same reports -> upsert, no new rows
    assert ShortInterestRecord.objects.filter(ticker="GME").count() == 2
    row = ShortInterestRecord.objects.get(ticker="GME", settlement_date=date(2026, 6, 30))
    assert row.shares_short == 25_000_000
    assert row.days_to_cover == pytest.approx(5.0)


@pytest.mark.django_db
def test_never_raises_per_ticker_failure():
    _watch("GME", "AMC")

    def _boom(ticker):
        if ticker == "AMC":
            raise RuntimeError("boom")
        return _ROWS

    with patch("apps.market.services.finra.fetch_short_interest", side_effect=_boom):
        result = refresh_short_interest()
    assert result["created"] == 2  # GME still ingested
```

- [ ] Run all three — expect failures:

```bash
docker compose exec web pytest apps/market/tests/test_ingest_iv_summary.py apps/market/tests/test_refresh_short_interest.py apps/market/tests/test_ingest_daily_bars.py -v
# EXPECTED: ImportError: cannot import name 'ingest_iv_summary' / 'refresh_short_interest'
#           and test_universe_coverage_and_timeframe FAILS on bars==300
```

- [ ] Implement in `backend/apps/market/tasks.py`. Replace the `ingest_daily_bars` body (lines 109-130) with:

```python
@shared_task(name="market.ingest_daily_bars")
def ingest_daily_bars() -> dict:
    """Fetch + persist daily OHLCBar for a fixed universe (watchlist + sector ETFs +
    $SPX/QQQ + macro proxies). Idempotent via fetch_ohlc's update_or_create. Requests
    300 bars so 252-session lookbacks (mom_12_1, MA-200, IV-rank inputs) have history;
    densifies what relative-strength, sector-rotation, the backtester, the leaderboard,
    and unusual-options IV-z all read. Also rides a BreadthDaily capture ($ADVN/$DECN
    closes). Never raises -- a per-symbol failure is logged and skipped."""
    from apps.market.services.context import MACRO, SECTOR_ETFS
    from apps.market.services.ohlc import fetch_ohlc
    from apps.profiles.models import WatchlistSymbol

    watchlist = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    universe = sorted(
        {s.upper() for s in [*watchlist, "$SPX", "QQQ", *SECTOR_ETFS, *MACRO.values()] if s}
    )
    ingested = 0
    for sym in universe:
        try:
            fetch_ohlc(sym, timeframe="1d", bars=300)
            ingested += 1
        except Exception as exc:
            log.warning("market.ingest_daily_bars %s failed: %s", sym, exc)
    breadth_written = _capture_breadth_daily()
    return {"requested": len(universe), "ingested": ingested, "breadth": breadth_written}


def _capture_breadth_daily() -> bool:
    """Persist today's $ADVN/$DECN closes as a BreadthDaily row — the A/D input
    history behind ad_line_slope_20d. Schwab-only symbology: free-quote fallbacks
    can't resolve $-prefixed indices, so without Schwab the symbols are absent and
    no row is written (A/D signals stay None). Never raises."""
    from django.utils import timezone as dj_timezone

    from apps.market.models import BreadthDaily
    from apps.market.services.quotes import fetch_quotes

    try:
        quotes = fetch_quotes(["$ADVN", "$DECN"])
        advn = (quotes.get("$ADVN") or {}).get("last")
        decn = (quotes.get("$DECN") or {}).get("last")
        if advn is None or decn is None:
            return False
        BreadthDaily.objects.update_or_create(
            date=dj_timezone.now().date(),
            defaults={
                "advn_close": float(advn),
                "decn_close": float(decn),
                "net_ad": float(advn) - float(decn),
            },
        )
        return True
    except Exception as exc:
        log.warning("market.ingest_daily_bars breadth capture failed: %s", exc)
        return False
```

  Then append the two new tasks at the end of the file:

```python
@shared_task(name="market.ingest_iv_summary")
def ingest_iv_summary() -> dict:
    """Nightly distillation of each watchlist ticker's option chain into one
    compact IVDaily row (ticker, date) — the input history behind IV rank /
    percentile, which full-chain JSONB retention can't back. Tickers without a
    chain source (no Schwab/Tradier) are skipped silently; hv_20 comes from
    stored daily closes. Never raises — per-ticker failures logged + skipped."""
    from apps.market.models import IVDaily, OHLCBar
    from apps.market.services import indicator
    from apps.market.services.iv_summary import summarize_chain

    tickers = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    today = timezone.now().date()
    written = 0
    for sym in sorted({t.upper() for t in tickers if t}):
        try:
            summary = summarize_chain(sym)
            if summary is None:
                continue
            closes = [
                float(c)
                for c in reversed(
                    OHLCBar.objects.filter(ticker=sym, timeframe="1d")
                    .order_by("-ts")
                    .values_list("close", flat=True)[:21]
                )
            ]
            IVDaily.objects.update_or_create(
                ticker=sym,
                date=today,
                defaults={
                    "atm_iv": summary["atm_iv"],
                    "term_slope": summary["term_slope"],
                    "put_call_vol": summary["put_call_vol"],
                    "put_call_oi": summary["put_call_oi"],
                    "gex_total": summary["gex_total"],
                    "flip_strike": summary["flip_strike"],
                    "hv_20": indicator.hv(closes, period=20),
                },
            )
            written += 1
        except Exception as exc:
            log.warning("market.ingest_iv_summary %s failed: %s", sym, exc)
    return {"tickers": len(tickers), "written": written}


@shared_task(name="market.refresh_short_interest")
def refresh_short_interest() -> dict:
    """Daily upsert of FINRA short-interest reports for watchlist tickers.

    FINRA publishes ~twice monthly, so most runs are a no-op — the upsert on
    (ticker, settlement_date) only creates rows when a new report appeared.
    Never raises; per-ticker failures are logged and skipped."""
    from datetime import date as date_cls

    from apps.market.models import ShortInterestRecord
    from apps.market.services import finra

    tickers = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    created = 0
    for sym in sorted({t.upper() for t in tickers if t}):
        try:
            for row in finra.fetch_short_interest(sym):
                try:
                    settlement = date_cls.fromisoformat(row["settlement_date"])
                except (KeyError, TypeError, ValueError):
                    continue
                _, was_created = ShortInterestRecord.objects.update_or_create(
                    ticker=sym,
                    settlement_date=settlement,
                    defaults={
                        "shares_short": row.get("shares_short"),
                        "avg_daily_volume": row.get("avg_daily_volume"),
                        "days_to_cover": row.get("days_to_cover"),
                    },
                )
                created += int(was_created)
        except Exception as exc:
            log.warning("market.refresh_short_interest %s failed: %s", sym, exc)
    return {"tickers": len(tickers), "created": created}
```

  (`timezone` is already imported at `tasks.py:12` — `from django.utils import timezone`.)

- [ ] Register both in `backend/config/celery.py` `beat_schedule` — after the `"ingest-daily-bars"` entry (line 105-108) add:

```python
    "ingest-iv-summary": {
        "task": "market.ingest_iv_summary",
        "schedule": crontab(hour=20, minute=45),  # after US close, before ingest-daily-bars
    },
    "refresh-short-interest": {
        "task": "market.refresh_short_interest",
        "schedule": crontab(hour=10, minute=0),
    },
```

- [ ] Inventory them in `backend/apps/core/scheduled_tasks.py` (SAME commit — drift gate). In the "daily batch / end-of-day" section, after the `market.refresh_events` entry (line 103-105), add:

```python
    ScheduledTask(
        "market.refresh_short_interest",
        "daily 10:00",
        "Upsert FINRA short-interest reports for watchlist tickers (new report ~twice monthly).",
        "",
    ),
    ScheduledTask(
        "market.ingest_iv_summary",
        "daily 20:45",
        "Distill each watchlist ticker's option chain into a compact IVDaily scalar row.",
        "",
    ),
```

  Update the module docstring line 3 `19 beat entries across a dozen apps` → `21 beat entries across a dozen apps`, and the same phrase in `backend/apps/core/tests/test_scheduled_work_inventory.py` line 3.

- [ ] Run the full set of gates + suites — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_ingest_iv_summary.py apps/market/tests/test_refresh_short_interest.py apps/market/tests/test_ingest_daily_bars.py apps/core/tests/test_scheduled_work_inventory.py apps/core/tests/test_celery_registration.py -v
# EXPECTED: all passed (inventory drift gate green with 21 entries)
```

- [ ] Commit (single commit — the drift gate demands beat + inventory together):

```bash
git add backend/apps/market/tasks.py backend/config/celery.py backend/apps/core/scheduled_tasks.py backend/apps/core/tests/test_scheduled_work_inventory.py backend/apps/market/tests/test_ingest_iv_summary.py backend/apps/market/tests/test_refresh_short_interest.py backend/apps/market/tests/test_ingest_daily_bars.py
git commit -m "feat(market): ingest_iv_summary + refresh_short_interest beat tasks; deepen bar ingest to 300 + BreadthDaily rider

Deploy note: worker/beat need 'docker compose restart worker beat' to see the new task modules.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Extend intel.RS_WINDOWS with 63/126/252

**Files:**
- Modify: `backend/apps/market/services/intel.py` (line 12)
- Test: extend `backend/apps/market/tests/test_intel.py`

**Interfaces:**
- Consumes: existing `return_over_sessions` / `relative_strength` (`intel.py:15-59`) — per-window values already degrade to `None` on thin data, so deeper windows are additive.
- Produces: `RS_WINDOWS = (1, 5, 20, 63, 126, 252)`. `relative_strength(ticker)` output `windows` dict now carries keys 63/126/252 (each `{"ticker_pct", "benchmark_pct", "rs"}`, `None`-filled until history is deep enough). `fetch_market_context`'s `relative_strength` payload grows the same keys — existing tests index specific windows and keep passing. Task 13's momentum family computes its own 63d RS via `return_over_sessions` (it does NOT depend on this tuple), but the breadth/context surface and P2+ do.

**Steps:**

- [ ] Add the failing test. Append to `backend/apps/market/tests/test_intel.py` (module already imports `pytest` and `relative_strength`; it defines bar helpers — this test is self-contained and only needs the import line at top of file: `from apps.market.services.intel import RS_WINDOWS` added alongside the existing intel imports):

```python
class TestDeepRsWindows:
    def test_rs_windows_include_quarter_half_year_and_year(self):
        assert RS_WINDOWS == (1, 5, 20, 63, 126, 252)

    @pytest.mark.django_db
    def test_deep_windows_degrade_to_none_on_thin_data(self):
        """With only a handful of bars, the deep windows are present but None —
        honest coverage, never invented."""
        _nvda_bars()
        _spx_bars()
        result = relative_strength("NVDA")
        assert result is not None
        w = result["windows"]
        assert set(w) == {1, 5, 20, 63, 126, 252}
        assert w[252]["ticker_pct"] is None
        assert w[252]["rs"] is None
```

  (`_nvda_bars` / `_spx_bars` are the module's existing fixture helpers — reuse them verbatim; they seed well under 63 bars.)

- [ ] Run — expect failure:

```bash
docker compose exec web pytest apps/market/tests/test_intel.py -k DeepRsWindows -v
# EXPECTED: AssertionError: assert (1, 5, 20) == (1, 5, 20, 63, 126, 252)
```

- [ ] Implement — in `backend/apps/market/services/intel.py` line 12, replace:

```python
RS_WINDOWS = (1, 5, 20)  # trading sessions
```

  with:

```python
RS_WINDOWS = (1, 5, 20, 63, 126, 252)  # trading sessions (day/week/month/quarter/half/year)
```

- [ ] Run the intel + context suites — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_intel.py apps/market/tests/test_services_context_intel.py apps/market/tests/test_services_context.py -v
# EXPECTED: all passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/intel.py backend/apps/market/tests/test_intel.py
git commit -m "feat(market): extend RS_WINDOWS to quarter/half-year/year horizons

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: signals package skeleton — bundles.py + shared data reads + engine cache kinds

**Files:**
- Create: `backend/apps/market/services/signals/__init__.py`, `backend/apps/market/services/signals/bundles.py`, `backend/apps/market/services/signals/_data.py`
- Modify: `backend/apps/market/cache.py` (`_TTL` — four `signals_*` kinds after the `"short_interest"` entry added in Task 5)
- Test: `backend/apps/market/tests/test_signals_bundles.py`

**Interfaces:**
- Consumes: `OHLCBar` (Decimal prices — `_data` converts to float).
- Produces (contract-pinned):
  ```python
  # apps/market/services/signals/bundles.py
  STRATEGY_TAGS = frozenset({"momentum", "mean_reversion", "vol_options", "positioning"})
  FAMILY_FOR_TAG = {t: t for t in STRATEGY_TAGS}   # identity today; the indirection is the point
  TRIGGER_PRESETS: dict[str, list[dict]]  # tag -> [{"label": str, "condition": <DSL dict>}]

  # apps/market/services/signals/_data.py (internal to the package)
  def daily_closes(ticker: str, n: int) -> list[float]   # oldest→newest, [] when none
  def daily_bars(ticker: str, n: int) -> list[dict]      # {"high","low","close"} floats, oldest→newest
  ```
  Cache kinds in `_TTL`: `"signals_momentum": 3600, "signals_reversion": 120, "signals_vol": 120, "signals_positioning": 3600`. P2 validates `TradingProfile.strategy_tags` against `STRATEGY_TAGS`; P3 renders `TRIGGER_PRESETS` as builder buttons (preset conditions reference the eight P3 DSL metrics; backtestable ones carry `"window": "1d"`, live-only ones omit `window` — the DSL's strict required-or-forbidden rule).

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_signals_bundles.py`:

```python
"""bundles vocabulary + tag routing + preset shape; signals cache-kind registration."""

from __future__ import annotations

from apps.market.cache import _TTL
from apps.market.services.signals import bundles


def test_strategy_tags_vocabulary():
    assert bundles.STRATEGY_TAGS == frozenset(
        {"momentum", "mean_reversion", "vol_options", "positioning"}
    )


def test_family_for_tag_is_total_over_tags():
    assert set(bundles.FAMILY_FOR_TAG) == set(bundles.STRATEGY_TAGS)
    for tag, family in bundles.FAMILY_FOR_TAG.items():
        assert family == tag  # identity today; the indirection is the point


def test_trigger_presets_cover_every_tag_with_valid_shape():
    assert set(bundles.TRIGGER_PRESETS) == set(bundles.STRATEGY_TAGS)
    for presets in bundles.TRIGGER_PRESETS.values():
        assert presets, "every tag ships at least one preset"
        for preset in presets:
            assert isinstance(preset["label"], str) and preset["label"]
            cond = preset["condition"]
            assert {"metric", "op", "value"} <= set(cond)


def test_signals_cache_kinds_registered():
    """Unregistered kinds silently default to 30s (cache.py:41) — every family
    kind must be registered or the free APIs get hammered."""
    assert _TTL["signals_momentum"] == 3600
    assert _TTL["signals_reversion"] == 120
    assert _TTL["signals_vol"] == 120
    assert _TTL["signals_positioning"] == 3600
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_signals_bundles.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.signals'
```

- [ ] Register the cache kinds. In `backend/apps/market/cache.py`, extend `_TTL` after `"short_interest": 21600,`:

```python
    # Signal-engine families: intraday-sensitive families short, daily-derived long.
    "signals_momentum": 3600,
    "signals_reversion": 120,
    "signals_vol": 120,
    "signals_positioning": 3600,
```

- [ ] Create `backend/apps/market/services/signals/__init__.py`:

```python
"""Single signal engine: family math + strategy-tag routing.

One source of truth for signal computation, consumed by every surface
(snapshot section, trigger DSL, analytics panel, regime/coverage inputs).
Entry point: engine.compute_signals / engine.compute_market_signals.
"""
```

- [ ] Create `backend/apps/market/services/signals/_data.py`:

```python
"""Shared read-only data access for the family modules (stored OHLCBar only).

No network I/O here — families that need live/provider data (volatility's chain
scalars, positioning's Finnhub reads) go through their own never-raise services.
"""

from __future__ import annotations

from apps.market.models import OHLCBar


def daily_closes(ticker: str, n: int) -> list[float]:
    """Last `n` stored daily closes, oldest -> newest ([] when none)."""
    qs = (
        OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d")
        .order_by("-ts")
        .values_list("close", flat=True)[:n]
    )
    return [float(c) for c in reversed(list(qs))]


def daily_bars(ticker: str, n: int) -> list[dict]:
    """Last `n` stored daily bars as {"high","low","close"} floats, oldest -> newest."""
    qs = (
        OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d")
        .order_by("-ts")
        .values("high", "low", "close")[:n]
    )
    return [
        {"high": float(b["high"]), "low": float(b["low"]), "close": float(b["close"])}
        for b in reversed(list(qs))
    ]
```

- [ ] Create `backend/apps/market/services/signals/bundles.py`:

```python
"""Strategy-tag vocabulary + tag -> family routing + suggested trigger presets.

STRATEGY_TAGS is the validated vocabulary for TradingProfile.strategy_tags.
FAMILY_FOR_TAG is identity today; the indirection is the point — a future tag
(e.g. "swing") can map onto an existing family without a data migration.
TRIGGER_PRESETS surfaces as preset buttons in the trigger builder; conditions
reference the trigger-DSL signal metrics. Backtestable indicator metrics carry
"window": "1d" (window is strictly required-or-forbidden per metric); live-only
metrics omit it. "ticker" is a placeholder the builder fills in.
"""

from __future__ import annotations

STRATEGY_TAGS = frozenset({"momentum", "mean_reversion", "vol_options", "positioning"})

FAMILY_FOR_TAG: dict[str, str] = {t: t for t in STRATEGY_TAGS}

TRIGGER_PRESETS: dict[str, list[dict]] = {
    "momentum": [
        {
            "label": "ADX > 25 (trending)",
            "condition": {"metric": "adx", "ticker": "", "op": ">", "value": 25, "window": "1d"},
        },
        {
            "label": "MACD histogram crosses positive",
            "condition": {
                "metric": "macd_hist",
                "ticker": "",
                "op": "crosses_above",
                "value": 0,
                "window": "1d",
            },
        },
    ],
    "mean_reversion": [
        {
            "label": "Z-score < -2 (stretched down)",
            "condition": {"metric": "zscore", "ticker": "", "op": "<", "value": -2, "window": "1d"},
        },
        {
            "label": "%B > 1 (above upper band)",
            "condition": {
                "metric": "bollinger_pct_b",
                "ticker": "",
                "op": ">",
                "value": 1,
                "window": "1d",
            },
        },
    ],
    "vol_options": [
        {
            "label": "IV rank > 80 (rich vol)",
            "condition": {"metric": "iv_rank", "ticker": "", "op": ">", "value": 80},
        },
        {
            "label": "Put/call volume > 1.5 (heavy put flow)",
            "condition": {"metric": "put_call_vol", "ticker": "", "op": ">", "value": 1.5},
        },
    ],
    "positioning": [
        {
            "label": "Days-to-cover > 5 (squeeze fuel)",
            "condition": {"metric": "si_days_to_cover", "ticker": "", "op": ">", "value": 5},
        },
        {
            "label": "7d news sentiment < -0.2 (souring tape)",
            "condition": {"metric": "news_sentiment", "ticker": "", "op": "<", "value": -0.2},
        },
    ],
}
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signals_bundles.py -v
# EXPECTED: 4 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/ backend/apps/market/cache.py backend/apps/market/tests/test_signals_bundles.py
git commit -m "feat(market): signals package skeleton — bundles vocabulary, shared reads, cache kinds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 13: Momentum family module

**Files:**
- Create: `backend/apps/market/services/signals/momentum.py`
- Test: `backend/apps/market/tests/test_signals_momentum.py`

**Interfaces:**
- Consumes: Task 3 `indicator.macd_hist(closes)` / `indicator.adx(bars, period=14)`; existing `indicator.compute("SMA", closes, period=...)`; `intel.return_over_sessions(ticker, sessions)` (reads stored 1d `OHLCBar`, `None` on thin data); Task 12 `_data.daily_closes` / `_data.daily_bars`; `CompanyFundamentals.sector` (a coarse finnhubIndustry string — `fundamentals.py:73` writes finnhubIndustry into BOTH sector and industry).
- Produces (contract-pinned signal names):
  ```python
  SIGNALS = ("macd_hist", "adx", "rs_vs_spx", "rs_vs_sector", "ma_alignment", "mom_12_1")
  SECTOR_TO_ETF: dict[str, str]   # finnhubIndustry -> SPDR ETF; unmapped -> rs_vs_sector None
  def compute(ticker: str, *, benchmark: str = "$SPX") -> dict   # keys == SIGNALS
  ```
  Semantics: `rs_vs_spx` = 63-session return minus benchmark's (percentage points, rounded 4); `rs_vs_sector` = same vs the mapped sector ETF; `ma_alignment` ∈ {"bullish","bearish","mixed",None} from SMA 20/50/200 ordering; `mom_12_1` = % return close[-252]→close[-21] (12-month momentum excluding the last month), `None` under 252 closes. Every signal independently `None` on thin data.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_signals_momentum.py`:

```python
"""Momentum family math (stored-OHLC only; None on thin data)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.market.models import CompanyFundamentals, OHLCBar
from apps.market.services.signals import momentum


def _seed_bars(ticker: str, closes: list[float]) -> None:
    now = timezone.now()
    OHLCBar.objects.bulk_create(
        OHLCBar(
            ticker=ticker,
            timeframe="1d",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1_000_000,
            ts=now - timedelta(days=len(closes) - i),
        )
        for i, c in enumerate(closes)
    )


@pytest.mark.django_db
def test_no_data_yields_all_none_with_full_keyset():
    out = momentum.compute("ZZZZ")
    assert set(out) == set(momentum.SIGNALS)
    assert all(v is None for v in out.values())


@pytest.mark.django_db
def test_rising_series_reads_bullish():
    closes = [100.0 + i * 0.5 for i in range(260)]
    _seed_bars("NVDA", closes)
    _seed_bars("$SPX", [5000.0] * 260)  # flat benchmark

    out = momentum.compute("NVDA")

    assert out["ma_alignment"] == "bullish"
    assert out["macd_hist"] is not None
    assert out["adx"] is not None and 0 <= out["adx"] <= 100
    assert out["rs_vs_spx"] is not None and out["rs_vs_spx"] > 0
    # close[-252] -> close[-21]: (229.5 - 114.0) / 114.0 * 100 with the 0.5 step
    assert out["mom_12_1"] == pytest.approx(
        (closes[-21] - closes[-252]) / closes[-252] * 100, rel=1e-6
    )


@pytest.mark.django_db
def test_rs_vs_sector_uses_fundamentals_sector_map():
    _seed_bars("NVDA", [100.0 + i for i in range(70)])
    _seed_bars("XLK", [100.0] * 70)  # flat sector ETF
    CompanyFundamentals.objects.create(ticker="NVDA", sector="Technology")

    out = momentum.compute("NVDA")
    assert out["rs_vs_sector"] is not None and out["rs_vs_sector"] > 0


@pytest.mark.django_db
def test_rs_vs_sector_none_when_sector_unmapped():
    _seed_bars("NVDA", [100.0 + i for i in range(70)])
    CompanyFundamentals.objects.create(ticker="NVDA", sector="Spelunking Equipment")

    assert momentum.compute("NVDA")["rs_vs_sector"] is None


@pytest.mark.django_db
def test_falling_series_reads_bearish():
    _seed_bars("BAD", [500.0 - i for i in range(260)])
    out = momentum.compute("BAD")
    assert out["ma_alignment"] == "bearish"
    assert out["mom_12_1"] is not None and out["mom_12_1"] < 0
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_signals_momentum.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.signals.momentum'
```

- [ ] Create `backend/apps/market/services/signals/momentum.py`:

```python
"""Momentum / trend family math. Stored-data only; every signal None on thin data."""

from __future__ import annotations

from apps.market.services import indicator
from apps.market.services.intel import return_over_sessions
from apps.market.services.signals._data import daily_bars, daily_closes

SIGNALS = ("macd_hist", "adx", "rs_vs_spx", "rs_vs_sector", "ma_alignment", "mom_12_1")

# CompanyFundamentals.sector carries finnhubIndustry strings — a coarse map onto
# the SPDR sector ETFs the rotation surface already uses (context.SECTOR_ETFS).
# Unmapped sectors -> rs_vs_sector None (absent, never invented).
SECTOR_TO_ETF: dict[str, str] = {
    "Technology": "XLK",
    "Semiconductors": "XLK",
    "Communication Services": "XLC",
    "Media": "XLC",
    "Telecommunication": "XLC",
    "Financial Services": "XLF",
    "Banking": "XLF",
    "Insurance": "XLF",
    "Energy": "XLE",
    "Health Care": "XLV",
    "Pharmaceuticals": "XLV",
    "Biotechnology": "XLV",
    "Life Sciences Tools & Services": "XLV",
    "Consumer Cyclical": "XLY",
    "Retail": "XLY",
    "Hotels, Restaurants & Leisure": "XLY",
    "Automobiles": "XLY",
    "Consumer Defensive": "XLP",
    "Beverages": "XLP",
    "Food Products": "XLP",
    "Industrials": "XLI",
    "Machinery": "XLI",
    "Aerospace & Defense": "XLI",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Chemicals": "XLB",
    "Metals & Mining": "XLB",
    "Real Estate": "XLRE",
}

_RS_WINDOW = 63  # sessions (~one quarter)


def _rs(ticker: str, other: str) -> float | None:
    """Ticker's 63-session return minus `other`'s, in percentage points."""
    t = return_over_sessions(ticker, _RS_WINDOW)
    o = return_over_sessions(other, _RS_WINDOW)
    if t is None or o is None:
        return None
    return round(t - o, 4)


def _sector_etf(ticker: str) -> str | None:
    from apps.market.models import CompanyFundamentals

    row = CompanyFundamentals.objects.filter(ticker=ticker).first()
    if row is None or not row.sector:
        return None
    return SECTOR_TO_ETF.get(row.sector)


def _ma_alignment(closes: list[float]) -> str | None:
    """20/50/200-SMA stack state: "bullish" (20>50>200), "bearish" (20<50<200),
    else "mixed"; None when any SMA lacks history."""
    s20 = indicator.compute("SMA", closes, period=20)
    s50 = indicator.compute("SMA", closes, period=50)
    s200 = indicator.compute("SMA", closes, period=200)
    if s20 is None or s50 is None or s200 is None:
        return None
    if s20 > s50 > s200:
        return "bullish"
    if s20 < s50 < s200:
        return "bearish"
    return "mixed"


def _mom_12_1(closes: list[float]) -> float | None:
    """12-month return excluding the most recent month (close[-252] -> close[-21])."""
    if len(closes) < 252:
        return None
    start, end = closes[-252], closes[-21]
    if not start:
        return None
    return round((end - start) / start * 100, 4)


def compute(ticker: str, *, benchmark: str = "$SPX") -> dict:
    """All momentum signals for `ticker`. Missing inputs -> None per signal."""
    ticker = ticker.upper()
    closes = daily_closes(ticker, 300)
    bars = daily_bars(ticker, 60)
    etf = _sector_etf(ticker)
    return {
        "macd_hist": indicator.macd_hist(closes),
        "adx": indicator.adx(bars, period=14),
        "rs_vs_spx": _rs(ticker, benchmark),
        "rs_vs_sector": _rs(ticker, etf) if etf else None,
        "ma_alignment": _ma_alignment(closes),
        "mom_12_1": _mom_12_1(closes),
    }
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signals_momentum.py -v
# EXPECTED: 5 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/momentum.py backend/apps/market/tests/test_signals_momentum.py
git commit -m "feat(market): momentum signal family (macd_hist/adx/rs/ma_alignment/mom_12_1)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 14: Mean-reversion family module

**Files:**
- Create: `backend/apps/market/services/signals/reversion.py`
- Test: `backend/apps/market/tests/test_signals_reversion.py`

**Interfaces:**
- Consumes: Task 3 `indicator.zscore` / `indicator.pct_b`; existing `indicator.compute("RSI", closes, period=2)`; Task 12 `_data.daily_closes`; stored intraday `OHLCBar` (`timeframe="5m"`) for session VWAP.
- Produces (contract-pinned):
  ```python
  SIGNALS = ("zscore_20d", "bollinger_pct_b", "rsi2", "dist_vwap_pct", "consec_days")
  def compute(ticker: str, *, benchmark: str = "$SPX") -> dict   # keys == SIGNALS
  ```
  Semantics: `zscore_20d`/`bollinger_pct_b` are the fixed period-20 engine values (the P3 DSL metrics are the parameterized generalization). `dist_vwap_pct` = % distance of the latest stored 5m close from today's volume-weighted average price; `None` off-hours / when no intraday bars were stored today (this module performs no fetches). `consec_days` = signed run length of consecutive up(+)/down(−) closes, 0 when the last close was flat, `None` under 2 closes.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_signals_reversion.py`:

```python
"""Mean-reversion family math (stored-OHLC only; None on thin data)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.market.models import OHLCBar
from apps.market.services.signals import reversion


def _seed_daily(ticker: str, closes: list[float]) -> None:
    now = timezone.now()
    OHLCBar.objects.bulk_create(
        OHLCBar(
            ticker=ticker,
            timeframe="1d",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1_000_000,
            ts=now - timedelta(days=len(closes) - i),
        )
        for i, c in enumerate(closes)
    )


def _seed_5m_today(ticker: str, closes_volumes: list[tuple[float, int]]) -> None:
    base = timezone.now().replace(hour=14, minute=0, second=0, microsecond=0)
    OHLCBar.objects.bulk_create(
        OHLCBar(
            ticker=ticker,
            timeframe="5m",
            open=c,
            high=c,
            low=c,
            close=c,
            volume=v,
            ts=base + timedelta(minutes=5 * i),
        )
        for i, (c, v) in enumerate(closes_volumes)
    )


@pytest.mark.django_db
def test_no_data_yields_all_none_with_full_keyset():
    out = reversion.compute("ZZZZ")
    assert set(out) == set(reversion.SIGNALS)
    assert all(v is None for v in out.values())


@pytest.mark.django_db
def test_stretched_down_series_reads_oversold():
    closes = [100.0] * 40 + [90.0, 85.0, 80.0]
    _seed_daily("AAPL", closes)

    out = reversion.compute("AAPL")

    assert out["zscore_20d"] is not None and out["zscore_20d"] < -1.5
    assert out["bollinger_pct_b"] is not None and out["bollinger_pct_b"] < 0.2
    assert out["rsi2"] is not None and out["rsi2"] < 10.0
    assert out["consec_days"] == -3  # three consecutive down closes


@pytest.mark.django_db
def test_consec_days_positive_run_and_flat():
    _seed_daily("UP", [100.0, 101.0, 102.0, 103.0])
    assert reversion.compute("UP")["consec_days"] == 3

    _seed_daily("FLAT", [100.0, 101.0, 101.0])
    assert reversion.compute("FLAT")["consec_days"] == 0


@pytest.mark.django_db
def test_dist_vwap_from_todays_5m_bars():
    # VWAP = (100*100 + 102*300) / 400 = 101.5; last close 102 -> +0.4926%
    _seed_5m_today("AAPL", [(100.0, 100), (102.0, 300)])
    out = reversion.compute("AAPL")
    assert out["dist_vwap_pct"] == pytest.approx((102.0 - 101.5) / 101.5 * 100, rel=1e-4)


@pytest.mark.django_db
def test_dist_vwap_none_without_todays_intraday_bars():
    _seed_daily("AAPL", [100.0] * 30)  # daily only — no 5m bars today
    assert reversion.compute("AAPL")["dist_vwap_pct"] is None
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_signals_reversion.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.signals.reversion'
```

- [ ] Create `backend/apps/market/services/signals/reversion.py`:

```python
"""Mean-reversion family math. Stored-data only; every signal None on thin data."""

from __future__ import annotations

from django.utils import timezone

from apps.market.services import indicator
from apps.market.services.signals._data import daily_closes

SIGNALS = ("zscore_20d", "bollinger_pct_b", "rsi2", "dist_vwap_pct", "consec_days")


def _dist_vwap_pct(ticker: str) -> float | None:
    """Percent distance of the latest stored 5m close from today's session VWAP.

    Reads stored intraday bars only (nothing is fetched here) — None off-hours
    or when no 5m bars were captured today. Honest absence, never invented.
    """
    from apps.market.models import OHLCBar

    today = timezone.now().date()
    rows = list(
        OHLCBar.objects.filter(ticker=ticker, timeframe="5m", ts__date=today)
        .order_by("ts")
        .values_list("close", "volume")
    )
    if not rows:
        return None
    pv = sum(float(c) * v for c, v in rows)
    vol = sum(v for _, v in rows)
    if vol <= 0:
        return None
    vwap = pv / vol
    if not vwap:
        return None
    last = float(rows[-1][0])
    return round((last - vwap) / vwap * 100, 4)


def _consec_days(closes: list[float]) -> int | None:
    """Signed run length of consecutive up(+)/down(-) closes; 0 when the last
    close was flat. None with fewer than 2 closes."""
    if len(closes) < 2:
        return None
    diffs = [b - a for a, b in zip(closes, closes[1:], strict=False)]
    last = diffs[-1]
    if last == 0:
        return 0
    sign = 1 if last > 0 else -1
    run = 0
    for d in reversed(diffs):
        if (d > 0 and sign == 1) or (d < 0 and sign == -1):
            run += 1
        else:
            break
    return sign * run


def compute(ticker: str, *, benchmark: str = "$SPX") -> dict:
    """All mean-reversion signals for `ticker`. Missing inputs -> None per signal.

    `benchmark` is unused here — kept for the uniform family signature.
    """
    ticker = ticker.upper()
    closes = daily_closes(ticker, 60)
    return {
        "zscore_20d": indicator.zscore(closes, period=20),
        "bollinger_pct_b": indicator.pct_b(closes, period=20, num_std=2.0),
        "rsi2": indicator.compute("RSI", closes, period=2),
        "dist_vwap_pct": _dist_vwap_pct(ticker),
        "consec_days": _consec_days(closes),
    }
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signals_reversion.py -v
# EXPECTED: 5 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/reversion.py backend/apps/market/tests/test_signals_reversion.py
git commit -m "feat(market): mean-reversion signal family (zscore/pct_b/rsi2/vwap/consec_days)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 15: Volatility / options-flow family module

**Files:**
- Create: `backend/apps/market/services/signals/volatility.py`
- Test: `backend/apps/market/tests/test_signals_volatility.py`

**Interfaces:**
- Consumes: Task 1 `IVDaily`; Task 3 `indicator.hv`; Task 9 `summarize_chain(ticker) -> dict | None` (keys `atm_iv/term_slope/put_call_vol/put_call_oi/gex_total/flip_strike/spot`); Task 12 `_data.daily_closes`.
- Produces (contract-pinned):
  ```python
  SIGNALS = ("iv_rank_252", "iv_percentile_252", "hv_20", "hv_iv_spread", "term_slope",
             "put_call_vol", "put_call_oi", "gex_total", "dist_to_flip_pct")
  def compute(ticker: str, *, benchmark: str = "$SPX") -> dict   # keys == SIGNALS
  def iv_rank_n(ticker: str) -> int   # IVDaily rows backing the rank (P4's meta.iv_rank_n)
  ```
  Semantics: `iv_rank_252`/`iv_percentile_252` over up to 252 `IVDaily.atm_iv` rows; **both None below 60 rows** (a young series must not read as a full-year rank); `iv_rank_n` exposes the row count so P4 can label it. Live chain scalars come from `summarize_chain`; when no chain is fetchable they fall back to the most recent IVDaily row (stale but honest), and to nothing when that's absent too. `hv_iv_spread` = `hv_20 − atm_iv` (both in percent units — Schwab's `volatility` is a percent). `dist_to_flip_pct` = `(spot − flip_strike)/spot·100` (positive ⇒ spot above the flip, dealer-stabilizing zone); spot falls back to the last stored close when the chain didn't carry one.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_signals_volatility.py`:

```python
"""Volatility family math: IV rank gating, chain scalars, fallbacks."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.market.models import IVDaily, OHLCBar
from apps.market.services.signals import volatility

_SUMMARY = {
    "atm_iv": 30.0,
    "term_slope": 5.0,
    "put_call_vol": 1.1,
    "put_call_oi": 0.9,
    "gex_total": 1_000_000.0,
    "flip_strike": 190.0,
    "spot": 200.0,
}


def _seed_iv(ticker: str, n: int, *, last_iv: float = 30.0) -> None:
    """n IVDaily rows: atm_iv ramps 10.0 -> 50.0, newest row = last_iv."""
    start = date(2026, 7, 1) - timedelta(days=n)
    rows = []
    for i in range(n):
        iv = 10.0 + (40.0 * i / max(n - 1, 1))
        rows.append(IVDaily(ticker=ticker, date=start + timedelta(days=i), atm_iv=iv))
    rows[-1].atm_iv = last_iv
    IVDaily.objects.bulk_create(rows)


def _seed_closes(ticker: str, closes: list[float]) -> None:
    now = timezone.now()
    OHLCBar.objects.bulk_create(
        OHLCBar(
            ticker=ticker,
            timeframe="1d",
            open=c,
            high=c + 1,
            low=c - 1,
            close=c,
            volume=1_000_000,
            ts=now - timedelta(days=len(closes) - i),
        )
        for i, c in enumerate(closes)
    )


@pytest.mark.django_db
def test_rank_none_below_60_rows_and_n_labeled():
    _seed_iv("AAPL", 59)
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=None):
        out = volatility.compute("AAPL")
    assert out["iv_rank_252"] is None
    assert out["iv_percentile_252"] is None
    assert volatility.iv_rank_n("AAPL") == 59


@pytest.mark.django_db
def test_rank_and_percentile_with_enough_rows():
    _seed_iv("AAPL", 100, last_iv=30.0)  # series spans 10..50; current 30 -> rank 50
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=None):
        out = volatility.compute("AAPL")
    assert out["iv_rank_252"] == pytest.approx(50.0, abs=1.0)
    assert out["iv_percentile_252"] is not None and 0.0 <= out["iv_percentile_252"] <= 100.0
    assert volatility.iv_rank_n("AAPL") == 100


@pytest.mark.django_db
def test_live_chain_scalars_and_derived_values():
    _seed_closes("AAPL", [200.0] * 25)
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=_SUMMARY):
        out = volatility.compute("AAPL")

    assert out["term_slope"] == pytest.approx(5.0)
    assert out["put_call_vol"] == pytest.approx(1.1)
    assert out["put_call_oi"] == pytest.approx(0.9)
    assert out["gex_total"] == pytest.approx(1_000_000.0)
    # dist_to_flip: (200 - 190) / 200 * 100 = 5%
    assert out["dist_to_flip_pct"] == pytest.approx(5.0)
    # flat closes -> hv_20 == 0; spread = 0 - 30 = -30
    assert out["hv_20"] == pytest.approx(0.0)
    assert out["hv_iv_spread"] == pytest.approx(-30.0)


@pytest.mark.django_db
def test_falls_back_to_latest_ivdaily_when_no_chain():
    IVDaily.objects.create(
        ticker="AAPL",
        date=date(2026, 7, 1),
        atm_iv=28.0,
        term_slope=3.0,
        put_call_vol=1.2,
        put_call_oi=0.8,
        gex_total=500.0,
        flip_strike=195.0,
    )
    _seed_closes("AAPL", [200.0] * 25)
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=None):
        out = volatility.compute("AAPL")

    assert out["term_slope"] == pytest.approx(3.0)
    assert out["put_call_vol"] == pytest.approx(1.2)
    assert out["gex_total"] == pytest.approx(500.0)
    # spot falls back to the last stored close (200) -> (200-195)/200*100 = 2.5
    assert out["dist_to_flip_pct"] == pytest.approx(2.5)


@pytest.mark.django_db
def test_no_data_yields_all_none_with_full_keyset():
    with patch("apps.market.services.iv_summary.summarize_chain", return_value=None):
        out = volatility.compute("ZZZZ")
    assert set(out) == set(volatility.SIGNALS)
    assert all(v is None for v in out.values())
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_signals_volatility.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.signals.volatility'
```

- [ ] Create `backend/apps/market/services/signals/volatility.py`:

```python
"""Volatility / options-flow family math.

IV rank/percentile read the IVDaily input history and are None below
_MIN_RANK_ROWS rows — a young series must never read as a full-year rank
(`iv_rank_n` exposes the row count so consumers can label it). Live chain
scalars come from the shared summarize_chain distillation; with no fetchable
chain they fall back to the most recent IVDaily row (stale but honest).
Units: atm_iv / hv_20 are both percent (Schwab volatility convention), so
hv_iv_spread is percentage points.
"""

from __future__ import annotations

from apps.market.services import indicator
from apps.market.services.signals._data import daily_closes

SIGNALS = (
    "iv_rank_252",
    "iv_percentile_252",
    "hv_20",
    "hv_iv_spread",
    "term_slope",
    "put_call_vol",
    "put_call_oi",
    "gex_total",
    "dist_to_flip_pct",
)

_MIN_RANK_ROWS = 60
_RANK_WINDOW = 252


def _iv_series(ticker: str) -> list[float]:
    """Up to 252 stored atm_iv values, oldest -> newest."""
    from apps.market.models import IVDaily

    qs = (
        IVDaily.objects.filter(ticker=ticker.upper(), atm_iv__isnull=False)
        .order_by("-date")
        .values_list("atm_iv", flat=True)[:_RANK_WINDOW]
    )
    return [float(v) for v in reversed(list(qs))]


def iv_rank_n(ticker: str) -> int:
    """IVDaily rows backing the rank — surfaced so a young rank is labeled."""
    return len(_iv_series(ticker))


def _rank_and_percentile(series: list[float]) -> tuple[float | None, float | None]:
    if len(series) < _MIN_RANK_ROWS:
        return None, None
    current = series[-1]
    lo, hi = min(series), max(series)
    rank = ((current - lo) / (hi - lo) * 100) if hi > lo else None
    percentile = sum(1 for v in series if v < current) / len(series) * 100
    return (round(rank, 2) if rank is not None else None, round(percentile, 2))


def _chain_scalars(ticker: str) -> dict:
    """Live chain scalars via summarize_chain; falls back to the most recent
    IVDaily row (stale but honest) when no chain is fetchable; {} when neither
    exists."""
    from apps.market.models import IVDaily
    from apps.market.services.iv_summary import summarize_chain

    summary = summarize_chain(ticker)
    if summary is not None:
        return summary
    row = IVDaily.objects.filter(ticker=ticker.upper()).order_by("-date").first()
    if row is None:
        return {}
    return {
        "atm_iv": row.atm_iv,
        "term_slope": row.term_slope,
        "put_call_vol": row.put_call_vol,
        "put_call_oi": row.put_call_oi,
        "gex_total": row.gex_total,
        "flip_strike": row.flip_strike,
        "spot": None,
    }


def compute(ticker: str, *, benchmark: str = "$SPX") -> dict:
    """All volatility signals for `ticker`. Missing inputs -> None per signal.

    `benchmark` is unused here — kept for the uniform family signature.
    """
    ticker = ticker.upper()
    rank, percentile = _rank_and_percentile(_iv_series(ticker))
    closes = daily_closes(ticker, 21)
    hv20 = indicator.hv(closes, period=20)
    scalars = _chain_scalars(ticker)
    atm_iv = scalars.get("atm_iv")
    spot = scalars.get("spot") or (closes[-1] if closes else None)
    flip = scalars.get("flip_strike")
    dist_to_flip = round((spot - flip) / spot * 100, 4) if spot and flip is not None else None
    hv_iv_spread = round(hv20 - atm_iv, 4) if hv20 is not None and atm_iv is not None else None
    return {
        "iv_rank_252": rank,
        "iv_percentile_252": percentile,
        "hv_20": hv20,
        "hv_iv_spread": hv_iv_spread,
        "term_slope": scalars.get("term_slope"),
        "put_call_vol": scalars.get("put_call_vol"),
        "put_call_oi": scalars.get("put_call_oi"),
        "gex_total": scalars.get("gex_total"),
        "dist_to_flip_pct": dist_to_flip,
    }
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signals_volatility.py -v
# EXPECTED: 5 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/volatility.py backend/apps/market/tests/test_signals_volatility.py
git commit -m "feat(market): volatility signal family (IV rank/percentile, HV, chain flow scalars)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 16: Positioning / sentiment family module (+ compute_market)

**Files:**
- Create: `backend/apps/market/services/signals/positioning.py`
- Test: `backend/apps/market/tests/test_signals_positioning.py`

**Interfaces:**
- Consumes: Task 1 `ShortInterestRecord` / `BreadthDaily` / `NewsItem.sentiment`; Task 7 `fundamentals.fetch_insider_transactions(ticker) -> {"net_90d": float|None, "buys": int, "sells": int} | {}` and `fundamentals.fetch_recommendations(ticker) -> list[dict]` (newest-first rows with `strongBuy/buy/hold/sell/strongSell` counts).
- Produces (contract-pinned):
  ```python
  SIGNALS = ("si_days_to_cover", "si_change_pct", "insider_net_90d",
             "analyst_rating_avg", "analyst_delta_30d", "news_sentiment_7d")
  MARKET_SIGNALS = ("ad_line_slope_20d",)
  def compute(ticker: str, *, benchmark: str = "$SPX") -> dict   # keys == SIGNALS
  def compute_market() -> dict                                    # keys == MARKET_SIGNALS
  ```
  Semantics: `si_change_pct` = % change in `shares_short` between the two latest reports (None with <2). `analyst_rating_avg` = count-weighted mean on 1–5 (strongSell=1 … strongBuy=5) of the newest recommendation row; `analyst_delta_30d` = newest minus the next (monthly) row. `news_sentiment_7d` = mean of non-null `NewsItem.sentiment` for the ticker over 7 days (None with none). `ad_line_slope_20d` = least-squares slope of the cumulative net_ad line over the last 20 `BreadthDaily` rows; None with <20 rows. Market-wide values live under the payload's `_market` key downstream — never per-ticker.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_signals_positioning.py`:

```python
"""Positioning family math: short interest, insiders, analysts, sentiment, A/D."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.market.models import BreadthDaily, NewsItem, ShortInterestRecord
from apps.market.services.signals import positioning

_RECS = [
    {"period": "2026-07-01", "strongBuy": 10, "buy": 20, "hold": 8, "sell": 2, "strongSell": 1},
    {"period": "2026-06-01", "strongBuy": 2, "buy": 8, "hold": 20, "sell": 8, "strongSell": 3},
]

def _patch_providers(insider=None, recs=None):
    return (
        patch(
            "apps.market.services.fundamentals.fetch_insider_transactions",
            return_value=insider if insider is not None else {},
        ),
        patch(
            "apps.market.services.fundamentals.fetch_recommendations",
            return_value=recs if recs is not None else [],
        ),
    )


@pytest.mark.django_db
def test_no_data_yields_all_none_with_full_keyset():
    p1, p2 = _patch_providers()
    with p1, p2:
        out = positioning.compute("ZZZZ")
    assert set(out) == set(positioning.SIGNALS)
    assert all(v is None for v in out.values())


@pytest.mark.django_db
def test_short_interest_signals():
    ShortInterestRecord.objects.create(
        ticker="GME", settlement_date=date(2026, 6, 15), shares_short=20_000_000, days_to_cover=4.0
    )
    ShortInterestRecord.objects.create(
        ticker="GME", settlement_date=date(2026, 6, 30), shares_short=25_000_000, days_to_cover=5.0
    )
    p1, p2 = _patch_providers()
    with p1, p2:
        out = positioning.compute("GME")
    assert out["si_days_to_cover"] == pytest.approx(5.0)  # newest report
    assert out["si_change_pct"] == pytest.approx(25.0)  # 20M -> 25M


@pytest.mark.django_db
def test_analyst_signals_weighted_average_and_delta():
    p1, p2 = _patch_providers(recs=_RECS)
    with p1, p2:
        out = positioning.compute("AAPL")
    # newest: (10*5 + 20*4 + 8*3 + 2*2 + 1*1) / 41 = 159/41
    assert out["analyst_rating_avg"] == pytest.approx(159 / 41, rel=1e-4)
    prior = (2 * 5 + 8 * 4 + 20 * 3 + 8 * 2 + 3 * 1) / 41  # 121/41
    assert out["analyst_delta_30d"] == pytest.approx(159 / 41 - prior, rel=1e-4)


@pytest.mark.django_db
def test_insider_net_flows_through():
    p1, p2 = _patch_providers(insider={"net_90d": 55_000.0, "buys": 4, "sells": 1})
    with p1, p2:
        out = positioning.compute("AAPL")
    assert out["insider_net_90d"] == pytest.approx(55_000.0)


@pytest.mark.django_db
def test_news_sentiment_7d_averages_only_scored_recent_items():
    now = timezone.now()

    def _news(eid, days_ago, sentiment):
        NewsItem.objects.create(
            provider="marketaux",
            external_id=eid,
            ticker="AAPL",
            headline="h",
            url="https://example.com/n",
            published_at=now - timedelta(days=days_ago),
            sentiment=sentiment,
        )

    _news("n1", 1, 0.4)
    _news("n2", 2, 0.2)
    _news("n3", 3, None)  # unscored — excluded, not treated as 0
    _news("n4", 30, -0.9)  # stale — outside the 7d window
    p1, p2 = _patch_providers()
    with p1, p2:
        out = positioning.compute("AAPL")
    assert out["news_sentiment_7d"] == pytest.approx(0.3)


@pytest.mark.django_db
def test_ad_line_slope_requires_20_rows_then_positive_on_advance():
    start = date(2026, 6, 1)
    for i in range(19):
        BreadthDaily.objects.create(date=start + timedelta(days=i), net_ad=100.0)
    assert positioning.compute_market()["ad_line_slope_20d"] is None

    BreadthDaily.objects.create(date=start + timedelta(days=19), net_ad=100.0)
    slope = positioning.compute_market()["ad_line_slope_20d"]
    # Constant +100 net_ad -> cumulative line rises 100/session -> slope 100.
    assert slope == pytest.approx(100.0)
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_signals_positioning.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.signals.positioning'
```

- [ ] Create `backend/apps/market/services/signals/positioning.py`:

```python
"""Positioning / sentiment family math.

Per-ticker inputs: ShortInterestRecord (FINRA), Finnhub insider/recommendation
fetchers (24h-cached, never raise), NewsItem.sentiment (Marketaux-only column).
Market-wide: BreadthDaily A/D line — exposed via compute_market() and carried
under the payload's reserved `_market` key downstream, never per-ticker.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

SIGNALS = (
    "si_days_to_cover",
    "si_change_pct",
    "insider_net_90d",
    "analyst_rating_avg",
    "analyst_delta_30d",
    "news_sentiment_7d",
)

MARKET_SIGNALS = ("ad_line_slope_20d",)

# 1-5 scale: strong sell -> strong buy (count-weighted mean over a Finnhub row).
_RATING_WEIGHTS = (
    ("strongSell", 1.0),
    ("sell", 2.0),
    ("hold", 3.0),
    ("buy", 4.0),
    ("strongBuy", 5.0),
)


def _short_interest(ticker: str) -> tuple[float | None, float | None]:
    """(days_to_cover of the newest report, % change in shares_short vs prior)."""
    from apps.market.models import ShortInterestRecord

    rows = list(
        ShortInterestRecord.objects.filter(ticker=ticker).order_by("-settlement_date")[:2]
    )
    if not rows:
        return None, None
    change = None
    if len(rows) == 2 and rows[0].shares_short and rows[1].shares_short:
        change = round(
            (rows[0].shares_short - rows[1].shares_short) / rows[1].shares_short * 100, 4
        )
    return rows[0].days_to_cover, change


def _rating_avg(row: dict) -> float | None:
    total = 0.0
    weighted = 0.0
    for key, weight in _RATING_WEIGHTS:
        try:
            count = float(row.get(key) or 0)
        except (TypeError, ValueError):
            count = 0.0
        total += count
        weighted += count * weight
    if total <= 0:
        return None
    return round(weighted / total, 4)


def _analyst(ticker: str) -> tuple[float | None, float | None]:
    """(newest count-weighted 1-5 rating, delta vs the prior monthly row)."""
    from apps.market.services.fundamentals import fetch_recommendations

    rows = fetch_recommendations(ticker)
    if not rows:
        return None, None
    latest = _rating_avg(rows[0])
    prior = _rating_avg(rows[1]) if len(rows) >= 2 else None
    delta = round(latest - prior, 4) if latest is not None and prior is not None else None
    return latest, delta


def _news_sentiment_7d(ticker: str) -> float | None:
    """Mean of non-null NewsItem.sentiment over 7 days — unscored items are
    excluded, never counted as 0."""
    from apps.market.models import NewsItem

    cutoff = timezone.now() - timedelta(days=7)
    scores = list(
        NewsItem.objects.filter(
            ticker=ticker, published_at__gte=cutoff, sentiment__isnull=False
        ).values_list("sentiment", flat=True)
    )
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _ad_line_slope_20d() -> float | None:
    """Least-squares slope of the 20-session cumulative A/D line (net_ad summed
    oldest -> newest). None with fewer than 20 BreadthDaily rows."""
    from apps.market.models import BreadthDaily

    rows = list(BreadthDaily.objects.filter(net_ad__isnull=False).order_by("-date")[:20])
    if len(rows) < 20:
        return None
    line: list[float] = []
    cum = 0.0
    for r in reversed(rows):
        cum += float(r.net_ad)
        line.append(cum)
    n = len(line)
    mean_x = (n - 1) / 2
    mean_y = sum(line) / n
    denom = sum((x - mean_x) ** 2 for x in range(n))
    if denom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in enumerate(line)) / denom
    return round(slope, 4)


def compute(ticker: str, *, benchmark: str = "$SPX") -> dict:
    """All per-ticker positioning signals. Missing inputs -> None per signal.

    `benchmark` is unused here — kept for the uniform family signature.
    """
    from apps.market.services.fundamentals import fetch_insider_transactions

    ticker = ticker.upper()
    dtc, si_change = _short_interest(ticker)
    rating, delta = _analyst(ticker)
    insider = fetch_insider_transactions(ticker)
    return {
        "si_days_to_cover": dtc,
        "si_change_pct": si_change,
        "insider_net_90d": insider.get("net_90d") if insider else None,
        "analyst_rating_avg": rating,
        "analyst_delta_30d": delta,
        "news_sentiment_7d": _news_sentiment_7d(ticker),
    }


def compute_market() -> dict:
    """Market-wide positioning signals (payload `_market` key, not per-ticker)."""
    return {"ad_line_slope_20d": _ad_line_slope_20d()}
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signals_positioning.py -v
# EXPECTED: 6 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/positioning.py backend/apps/market/tests/test_signals_positioning.py
git commit -m "feat(market): positioning signal family (short interest, insiders, analysts, sentiment, A/D)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 17: The engine — compute_signals + compute_market_signals

**Files:**
- Create: `backend/apps/market/services/signals/engine.py`
- Test: `backend/apps/market/tests/test_signals_engine.py`

**Interfaces:**
- Consumes: Task 12-16 family modules — each exposes `SIGNALS: tuple[str, ...]` and `compute(ticker, *, benchmark="$SPX") -> dict`; `positioning` additionally `MARKET_SIGNALS` + `compute_market() -> dict`; `apps.market.cache.get_or_fetch` / `ttl_for_kind` with the four `signals_*` kinds.
- Produces (contract-pinned — P2/P3/P4/P5 all consume exactly this):
  ```python
  # apps/market/services/signals/engine.py
  FAMILIES = ("momentum", "mean_reversion", "vol_options", "positioning")

  def compute_signals(
      ticker: str,
      families: list[str] | None = None,   # None => all four
      *,
      benchmark: str = "$SPX",
  ) -> dict[str, dict[str, float | int | str | None]]:
      """{family: {signal_name: value|None}}. Never raises. Redis-cached per (family, ticker)."""

  def compute_market_signals() -> dict[str, float | None]:
      """Market-wide signals (currently {"ad_line_slope_20d": ...}). Never raises."""
  ```
  Redis key shape (law): `market:signals:{family}:{ticker}`; market-wide uses the reserved pseudo-ticker `_market` under the positioning kind. A family-module exception degrades to an all-`None` dict over that family's full `SIGNALS` keyset; a Redis outage degrades to an uncached compute. Values are JSON-safe (float/int/str/None) so the cache round-trip is lossless.

**Steps:**

- [ ] Write the failing test `backend/apps/market/tests/test_signals_engine.py`:

```python
"""compute_signals: family selection, never-raises degradation, cache keying."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.services.signals import engine

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}


def test_families_constant_pins_the_contract():
    assert engine.FAMILIES == ("momentum", "mean_reversion", "vol_options", "positioning")


@pytest.mark.django_db
def test_default_computes_all_four_families():
    with patch("apps.market.services.signals.engine.cache.get_or_fetch", **_PASSTHRU):
        out = engine.compute_signals("ZZZZ")
    assert set(out) == set(engine.FAMILIES)
    # Unknown ticker, empty DB: every signal present and None (full keysets).
    from apps.market.services.signals import momentum, positioning, reversion, volatility

    assert set(out["momentum"]) == set(momentum.SIGNALS)
    assert set(out["mean_reversion"]) == set(reversion.SIGNALS)
    assert set(out["vol_options"]) == set(volatility.SIGNALS)
    assert set(out["positioning"]) == set(positioning.SIGNALS)


@pytest.mark.django_db
def test_families_filter_and_unknown_names_ignored():
    with patch("apps.market.services.signals.engine.cache.get_or_fetch", **_PASSTHRU):
        out = engine.compute_signals("ZZZZ", families=["momentum", "bogus"])
    assert set(out) == {"momentum"}


@pytest.mark.django_db
def test_family_module_exception_degrades_to_all_none():
    with (
        patch("apps.market.services.signals.engine.cache.get_or_fetch", **_PASSTHRU),
        patch(
            "apps.market.services.signals.momentum.compute",
            side_effect=RuntimeError("boom"),
        ),
    ):
        out = engine.compute_signals("AAPL", families=["momentum"])
    from apps.market.services.signals import momentum

    assert out["momentum"] == dict.fromkeys(momentum.SIGNALS)


@pytest.mark.django_db
def test_cache_key_and_kind_per_family():
    calls: list[tuple[str, int]] = []

    def _record(key, *, ttl_seconds, fetcher):
        calls.append((key, ttl_seconds))
        return fetcher()

    with patch("apps.market.services.signals.engine.cache.get_or_fetch", side_effect=_record):
        engine.compute_signals("aapl", families=["momentum", "vol_options"])

    assert ("market:signals:momentum:AAPL", 3600) in calls
    assert ("market:signals:vol_options:AAPL", 120) in calls


@pytest.mark.django_db
def test_redis_outage_degrades_to_uncached_compute():
    with patch(
        "apps.market.services.signals.engine.cache.get_or_fetch",
        side_effect=ConnectionError("redis down"),
    ):
        out = engine.compute_signals("ZZZZ", families=["mean_reversion"])
    from apps.market.services.signals import reversion

    assert set(out["mean_reversion"]) == set(reversion.SIGNALS)


@pytest.mark.django_db
def test_market_signals_shape_and_key():
    calls: list[str] = []

    def _record(key, *, ttl_seconds, fetcher):
        calls.append(key)
        return fetcher()

    with patch("apps.market.services.signals.engine.cache.get_or_fetch", side_effect=_record):
        out = engine.compute_market_signals()

    assert calls == ["market:signals:positioning:_market"]
    assert set(out) == {"ad_line_slope_20d"}


@pytest.mark.django_db
def test_market_signals_never_raise():
    with (
        patch("apps.market.services.signals.engine.cache.get_or_fetch", **_PASSTHRU),
        patch(
            "apps.market.services.signals.positioning.compute_market",
            side_effect=RuntimeError("boom"),
        ),
    ):
        out = engine.compute_market_signals()
    assert out == {"ad_line_slope_20d": None}
```

- [ ] Run — expect ModuleNotFoundError:

```bash
docker compose exec web pytest apps/market/tests/test_signals_engine.py -v
# EXPECTED: ModuleNotFoundError: No module named 'apps.market.services.signals.engine'
```

- [ ] Create `backend/apps/market/services/signals/engine.py`:

```python
"""compute_signals — the single signal-engine entry point.

{family: {signal_name: value|None}}. Never raises: a family-module error
degrades to an all-None dict over that family's full SIGNALS keyset (absent,
never invented), and a Redis outage degrades to an uncached compute. Results
are cached per (family, ticker) under market:signals:{family}:{ticker} with
per-family TTLs registered in apps.market.cache._TTL. Values are JSON-safe
(float/int/str/None) so the cache round-trip is lossless.
"""

from __future__ import annotations

import logging

from apps.market import cache
from apps.market.services.signals import momentum, positioning, reversion, volatility

log = logging.getLogger(__name__)

FAMILIES = ("momentum", "mean_reversion", "vol_options", "positioning")

_MODULES = {
    "momentum": momentum,
    "mean_reversion": reversion,
    "vol_options": volatility,
    "positioning": positioning,
}

# Cache kind per family — every kind is registered in cache._TTL (an
# unregistered kind silently defaults to 30s and hammers the free providers).
_CACHE_KIND = {
    "momentum": "signals_momentum",
    "mean_reversion": "signals_reversion",
    "vol_options": "signals_vol",
    "positioning": "signals_positioning",
}

# Reserved pseudo-ticker for market-wide signals (the payload's `_market` key).
_MARKET_KEY = "_market"


def _compute_family(family: str, ticker: str, benchmark: str) -> dict:
    module = _MODULES[family]
    try:
        values = module.compute(ticker, benchmark=benchmark)
    except Exception as exc:
        log.warning("market.signals.%s failed ticker=%s: %s", family, ticker, exc)
        return dict.fromkeys(module.SIGNALS)
    # Guarantee the full signal-name set so consumers can rely on the keys.
    return {name: values.get(name) for name in module.SIGNALS}


def compute_signals(
    ticker: str,
    families: list[str] | None = None,
    *,
    benchmark: str = "$SPX",
) -> dict[str, dict[str, float | int | str | None]]:
    """{family: {signal_name: value|None}} for `ticker`. Never raises.

    `families=None` computes all four; unknown family names are ignored.
    """
    ticker = (ticker or "").upper()
    selected = [f for f in (families if families is not None else FAMILIES) if f in _MODULES]
    out: dict[str, dict] = {}
    for family in selected:
        try:
            out[family] = cache.get_or_fetch(
                f"market:signals:{family}:{ticker}",
                ttl_seconds=cache.ttl_for_kind(_CACHE_KIND[family]),
                fetcher=lambda f=family: _compute_family(f, ticker, benchmark),
            )
        except Exception as exc:  # Redis down — compute uncached rather than raise
            log.warning("market.signals.cache failed family=%s: %s", family, exc)
            out[family] = _compute_family(family, ticker, benchmark)
    return out


def _compute_market() -> dict:
    try:
        return positioning.compute_market()
    except Exception as exc:
        log.warning("market.signals.market failed: %s", exc)
        return dict.fromkeys(positioning.MARKET_SIGNALS)


def compute_market_signals() -> dict[str, float | None]:
    """Market-wide signals (currently {"ad_line_slope_20d": ...}). Never raises."""
    try:
        return cache.get_or_fetch(
            f"market:signals:positioning:{_MARKET_KEY}",
            ttl_seconds=cache.ttl_for_kind("signals_positioning"),
            fetcher=_compute_market,
        )
    except Exception as exc:
        log.warning("market.signals.market cache failed: %s", exc)
        return _compute_market()
```

- [ ] Run — expect PASS:

```bash
docker compose exec web pytest apps/market/tests/test_signals_engine.py -v
# EXPECTED: 8 passed
```

- [ ] Commit:

```bash
git add backend/apps/market/services/signals/engine.py backend/apps/market/tests/test_signals_engine.py
git commit -m "feat(market): compute_signals engine — cached, never-raises family dispatch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 18: Phase verification — full gates + landmine checklist

**Files:** none created/modified (verification only; fix-forward if anything reds).

**Interfaces:**
- Consumes: everything above.
- Produces: a green P1. The spec's §12 landmine checklist items in P1 scope, verified against the working tree.

**Steps:**

- [ ] Full backend test run (CI parity — definition order):

```bash
docker compose exec web pytest -p no:randomly
# EXPECTED: all passed; coverage >= 86 (branch)
```

- [ ] Migration + inventory gates:

```bash
make check-migrations
# EXPECTED: exit 0
docker compose exec web pytest apps/core/tests/test_scheduled_work_inventory.py apps/core/tests/test_celery_registration.py apps/core/tests/test_feature_flag_inventory.py -v
# EXPECTED: all passed (21 beat entries mirrored; no new env.bool flags were added, so the
#           feature-flag inventory is untouched — retention knobs are env.int)
```

- [ ] Lint (ruff + mypy + import-linter + deptry + semgrep landmine rules):

```bash
make lint
# EXPECTED: exit 0. Notes if it reds:
# - import-linter: the signals package lives INSIDE apps.market, so the fungible-provider
#   contract is untouched; finra is intentionally NOT in forbidden_modules (distinct domain,
#   like edgar/treasury — see Global Constraints).
# - ruff C901 (<=15): _record-style loops in tasks.py are small; if ingest_iv_summary trips
#   C901, extract the closes-read into a module-level helper `_daily_closes_for_hv(sym)`.
# - semgrep rules: no `bytes(img.data)`, no `_safe(_, {})`, no `0.0.0.0`, no secret logging
#   were introduced; FINRA logging goes through safe_err.
```

- [ ] Spec §12 landmine checklist — verify each P1-scope item and check it off here:

  - [ ] Cache kinds registered in `_TTL` (`short_interest` + four `signals_*`): `docker compose exec web python -c "from apps.market.cache import _TTL; print({k: _TTL[k] for k in ('short_interest','signals_momentum','signals_reversion','signals_vol','signals_positioning')})"` — EXPECTED: `{'short_interest': 21600, 'signals_momentum': 3600, 'signals_reversion': 120, 'signals_vol': 120, 'signals_positioning': 3600}`.
  - [ ] Beat tasks in `scheduled_tasks.py` with the `market.` prefix (drift-gate test green above).
  - [ ] `safe_err` used in `finra.py` (keyless, but the template is followed): `grep -n safe_err backend/apps/market/services/finra.py` — EXPECTED: import + one call site.
  - [ ] `.gitignore` does not swallow the new package: `git check-ignore backend/apps/market/services/signals/engine.py; echo $?` — EXPECTED: `1` (not ignored).
  - [ ] IV rank honesty: `iv_rank_252`/`iv_percentile_252` None below 60 rows + `iv_rank_n` exposed (covered by `test_signals_volatility.py::test_rank_none_below_60_rows_and_n_labeled`).
  - [ ] Never-raises contracts: engine (`test_signals_engine.py`), tasks (`test_ingest_iv_summary.py::test_never_raises_per_ticker_failure`, `test_refresh_short_interest.py::test_never_raises_per_ticker_failure`), providers (per-module never-raises tests).

- [ ] MOCK_EXTERNAL sanity (fixtures only — do NOT set the flag on the dev stack; this runs a one-off pytest with the env var scoped to the test process):

```bash
docker compose exec -e MOCK_EXTERNAL=true web pytest apps/market/tests/test_finra.py::test_mock_mode_returns_canned_rows apps/market/tests/test_fundamentals_insider_recs.py::test_insider_mock_mode_returns_canned apps/market/tests/test_fundamentals_insider_recs.py::test_recommendations_mock_mode_returns_canned -v
# EXPECTED: 3 passed (each canned fixture short-circuits before any network)
```

- [ ] Restart worker/beat so the new task modules register (dev-stack deploy note; fresh `up`/CI unaffected):

```bash
docker compose restart worker beat
docker compose exec worker celery -A config inspect registered | grep -E "market.ingest_iv_summary|market.refresh_short_interest"
# EXPECTED: both task names listed
```

- [ ] If any fix was needed, commit it conventionally (`fix(market): ...`); otherwise nothing to commit — P1 is complete and independently shippable (nothing consumes the engine yet).

---

## Execution order & dependency notes

```
Task 1 (models) ──> Task 2 (retention)          Task 3 (indicators) ─┐
        │                                        Task 4 (fallback)   │
        ├──> Task 8 (marketaux sentiment)        Task 5 (finra) ──> Task 6 (catalog/probe)
        │                                        Task 7 (finnhub fetchers)
        └──> Task 9 (iv_summary) ──> Task 10 (beat tasks; also needs 3,4,5)
Task 11 (intel windows)   Task 12 (bundles/cache) ──> Tasks 13,14,15,16 (families; need 1,3,7,9)
Tasks 13-16 ──> Task 17 (engine) ──> Task 18 (verification)
```

Tasks 3, 4, 5, 7, 11 are mutually independent and may run in parallel workers; everything else follows the arrows. Every task leaves the suite green — commit points are safe stopping points.
