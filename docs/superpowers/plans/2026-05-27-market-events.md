# Market Events (earnings + curated macro) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a forward-looking `MarketEvent` store (per-ticker earnings + curated US macro) that enriches snapshots, powers a `days_to_earnings` trigger leaf, and surfaces on a new `/events` page.

**Architecture:** Extend `apps.market` with one polymorphic `MarketEvent` table (sibling to `NewsItem`) and an `events.py` service cloned from `news.py` (Finnhub + `MOCK_EXTERNAL` + Redis cache + seed fallback). A daily Celery beat task keeps the store fresh. The store is read by a new trigger metric, an opt-in `"events"` snapshot section, and a `GET /api/market/events/` endpoint feeding an `/events` page + dashboard badge.

**Tech Stack:** Django 5 + DRF, Celery, Redis, Postgres 16, Finnhub (`/calendar/earnings`, `/calendar/economic`); React 18 + TS, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-05-27-market-events-design.md`

---

## Conventions for this plan

- **The dev stack must be up:** `make dev`. All tests run inside containers.
- **Run one backend test** (WORKDIR is `/app/backend`, so drop the `backend/` prefix):
  `docker compose exec web pytest apps/<app>/tests/test_<x>.py -v`
- **Run one frontend test:**
  `docker compose exec frontend pnpm exec vitest run src/__tests__/<path> -t "<name>"`
- **Migrations:** `docker compose exec web python manage.py makemigrations market` then `docker compose exec web python manage.py migrate market`.
- **Commits:** conventional (`feat(market):`, `feat(triggers):`, etc.). End every commit message with the trailer:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
  If the lefthook pre-commit hook fails with container-relative paths, prefix with `LEFTHOOK=0`.
- **Worker/beat do NOT hot-reload** (only `web` + `frontend` do). After Task 5 adds the task + beat entry, run `docker compose restart worker beat` before exercising the scheduled task on the running stack.
- **`ty` is advisory**, not a gate. The real gates are `ruff` + `pytest` + frontend `eslint`/`tsc` + `vitest`.

## File structure

**Create:**
- `backend/apps/market/services/events.py` — Finnhub earnings + macro fetch, upsert, cache, mock, `upcoming_events` read helper.
- `backend/apps/market/services/events_seed.py` — `SEED_MACRO_EVENTS` fallback list.
- `backend/apps/market/tests/test_events_model.py`
- `backend/apps/market/tests/test_events_service.py`
- `backend/apps/market/tests/test_events_endpoint.py`
- `backend/apps/market/tests/test_refresh_events_task.py`
- `frontend/src/hooks/useUpcomingEvents.ts`
- `frontend/src/pages/EventsPage.tsx`
- `frontend/src/components/UpcomingEvents.tsx`
- `frontend/src/__tests__/hooks/useUpcomingEvents.test.tsx`

**Modify:**
- `backend/apps/market/models.py` — add `MarketEvent`.
- `backend/apps/market/cache.py` — add `"events"` TTL.
- `backend/apps/market/tasks.py` — add `refresh_events`.
- `backend/config/celery.py` — add beat entry.
- `backend/apps/triggers/dsl.py` — validate `days_to_earnings`.
- `backend/apps/triggers/evaluator.py` — `leaf_key` branch.
- `backend/apps/triggers/metrics.py` — resolve `days_to_earnings`.
- `backend/apps/triggers/services/describe.py` — phrasing.
- `backend/apps/snapshots/services/__init__.py` — `"events"` fetcher.
- `backend/apps/snapshots/serializer.py` — `"events"` renderer + title.
- `backend/apps/market/views.py` — `events` view.
- `backend/apps/market/urls.py` — `events/` route.
- `frontend/src/api/market.ts` — `fetchUpcomingEvents` + types.
- `frontend/src/router.tsx` — `/events` route.
- `frontend/src/components/layout/SideNav.tsx` — nav link.
- `frontend/src/components/layout/AppLayout.tsx` — `go-events` command.
- `frontend/src/hooks/useKeyboardShortcuts.ts` — `g e` shortcut.
- `frontend/src/pages/Dashboard.tsx` — mount `<UpcomingEvents>`.

---

### Task 1: `MarketEvent` model + migration + cache TTL

**Files:**
- Modify: `backend/apps/market/models.py`
- Modify: `backend/apps/market/cache.py:15-27`
- Create: `backend/apps/market/tests/test_events_model.py`
- Create: `backend/apps/market/migrations/0006_marketevent.py` (generated)

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_events_model.py`:

```python
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.market.models import MarketEvent


@pytest.mark.django_db
def test_market_event_dedups_on_source_external_id():
    now = timezone.now()
    MarketEvent.objects.create(
        source="finnhub", external_id="EARN:NVDA:2026-05-28", kind="earnings",
        ticker="NVDA", title="NVDA earnings", event_time=now + timedelta(days=2),
    )
    with pytest.raises(IntegrityError):
        MarketEvent.objects.create(
            source="finnhub", external_id="EARN:NVDA:2026-05-28", kind="earnings",
            ticker="NVDA", title="dup", event_time=now + timedelta(days=2),
        )


@pytest.mark.django_db
def test_market_event_orders_by_event_time():
    now = timezone.now()
    MarketEvent.objects.create(source="s", external_id="b", kind="cpi", title="CPI",
                               event_time=now + timedelta(days=5))
    MarketEvent.objects.create(source="s", external_id="a", kind="fomc", title="FOMC",
                               event_time=now + timedelta(days=1))
    titles = list(MarketEvent.objects.order_by("event_time").values_list("title", flat=True))
    assert titles == ["FOMC", "CPI"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_events_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'MarketEvent'`.

- [ ] **Step 3: Add the model**

In `backend/apps/market/models.py`, append:

```python
class MarketEvent(models.Model):
    """A scheduled market catalyst — per-ticker earnings or curated US macro. Deduped on (source, external_id)."""

    KINDS: ClassVar = [
        ("earnings", "earnings"), ("fomc", "fomc"), ("cpi", "cpi"),
        ("nfp", "nfp"), ("pce", "pce"), ("gdp", "gdp"),
    ]
    source = models.CharField(max_length=16)  # "finnhub" | "seed"
    external_id = models.CharField(max_length=80, db_index=True)
    kind = models.CharField(max_length=16, choices=KINDS)
    ticker = models.CharField(max_length=16, blank=True, default="", db_index=True)
    title = models.CharField(max_length=200)
    event_time = models.DateTimeField(db_index=True)
    when_hint = models.CharField(max_length=8, blank=True, default="")  # bmo|amc|""
    impact = models.CharField(max_length=8, blank=True, default="")  # high|medium|low
    detail = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["source", "external_id"], name="uniq_event_source_id"),
        ]
        indexes: ClassVar = [
            models.Index(fields=["ticker", "event_time"]),
            models.Index(fields=["kind", "event_time"]),
            models.Index(fields=["event_time"]),
        ]

    def __str__(self) -> str:
        return f"MarketEvent({self.kind}, {self.ticker or '-'}, {self.event_time:%Y-%m-%d})"
```

In `backend/apps/market/cache.py`, add `"events"` to `_TTL` (after `"context": 30,`):

```python
    "context": 30,
    "events": 3600,
```

- [ ] **Step 4: Generate + apply the migration, run tests**

Run:
```bash
docker compose exec web python manage.py makemigrations market
docker compose exec web python manage.py migrate market
docker compose exec web pytest apps/market/tests/test_events_model.py -v
```
Expected: migration `0006_marketevent.py` created; both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/models.py backend/apps/market/cache.py \
        backend/apps/market/migrations/0006_marketevent.py \
        backend/apps/market/tests/test_events_model.py
git commit -m "feat(market): add MarketEvent model + events cache TTL"
```

---

### Task 2: `events.py` — earnings fetch + mock + upsert

**Files:**
- Create: `backend/apps/market/services/events.py`
- Create: `backend/apps/market/tests/test_events_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_events_service.py`:

```python
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from apps.market.models import MarketEvent
from apps.market.services import events


def _soon(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


@pytest.mark.django_db
def test_fetch_earnings_parses_and_dedups():
    body = {"earningsCalendar": [
        {"symbol": "NVDA", "date": _soon(2), "hour": "amc",
         "epsEstimate": 0.84, "epsActual": None, "revenueEstimate": 2.6e10},
    ]}
    with (
        patch("apps.market.services.events._finnhub_get", return_value=body),
        patch("apps.market.services.events._finnhub_api_key", return_value="k"),
        patch("apps.market.services.events.cache.get_or_fetch",
              side_effect=lambda key, *, ttl_seconds, fetcher: fetcher()),
    ):
        events.fetch_earnings(["NVDA"])
        events.fetch_earnings(["NVDA"])  # second call: dedups

    rows = MarketEvent.objects.filter(kind="earnings", ticker="NVDA")
    assert rows.count() == 1
    e = rows.first()
    assert e.when_hint == "amc"
    assert e.title == "NVDA earnings (AMC)"
    assert e.detail["eps_est"] == 0.84


@pytest.mark.django_db
def test_fetch_earnings_no_credential_returns_empty():
    with patch("apps.market.services.events._finnhub_api_key", return_value=None):
        assert events.fetch_earnings(["NVDA"]) == []


@pytest.mark.django_db
def test_fetch_earnings_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        out = events.fetch_earnings(["IGNORED"])
    assert any(e.ticker == "NVDA" for e in out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_events_service.py -v`
Expected: FAIL with `ModuleNotFoundError: apps.market.services.events`.

- [ ] **Step 3: Create the earnings half of the service**

Create `backend/apps/market/services/events.py`:

```python
"""Market events: earnings dates + curated US macro. Mirrors news.py's source pattern."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.models import MarketEvent
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="finnhub")
    except ApiCredential.DoesNotExist:
        return None
    return (cred.token or {}).get("api_key")


def _finnhub_get(path: str, params: dict, api_key: str) -> dict:
    params = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def _earnings_event_time(d: str, hour: str) -> datetime:
    """Finnhub earnings calendar is date-only; place at a representative UTC time per session."""
    base = datetime.fromisoformat(d).replace(tzinfo=UTC)
    if hour == "bmo":
        return base.replace(hour=13, minute=0)   # ~before US open
    if hour == "amc":
        return base.replace(hour=21, minute=0)   # ~after US close
    return base.replace(hour=20, minute=0)        # unknown → end of US session


def _upsert_earnings(rows: list[dict]) -> list[MarketEvent]:
    out: list[MarketEvent] = []
    for r in rows:
        symbol = (r.get("symbol") or "").upper()
        d = r.get("date")
        if not symbol or not d:
            continue
        hour = (r.get("hour") or "").lower()
        labelled = hour in ("bmo", "amc")
        obj, _ = MarketEvent.objects.update_or_create(
            source="finnhub",
            external_id=f"EARN:{symbol}:{d}",
            defaults={
                "kind": "earnings",
                "ticker": symbol,
                "title": f"{symbol} earnings" + (f" ({hour.upper()})" if labelled else ""),
                "event_time": _earnings_event_time(d, hour),
                "when_hint": hour if labelled else "",
                "impact": "high",
                "detail": {
                    "eps_est": r.get("epsEstimate"),
                    "eps_actual": r.get("epsActual"),
                    "rev_est": r.get("revenueEstimate"),
                },
            },
        )
        out.append(obj)
    return out


def _canned_earnings() -> list[dict]:
    soon = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    return [{"symbol": "NVDA", "date": soon, "hour": "amc",
             "epsEstimate": 0.84, "epsActual": None, "revenueEstimate": 2.6e10}]


def fetch_earnings(tickers: list[str], *, ahead_days: int = 30) -> list[MarketEvent]:
    """Fetch + upsert upcoming earnings for `tickers`. Returns the upserted rows."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _upsert_earnings(_canned_earnings())

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("Finnhub credential not configured; no earnings fetched")
        return []

    today = datetime.now(UTC).date()
    end = today + timedelta(days=ahead_days)
    out: list[MarketEvent] = []
    for ticker in [t.upper() for t in tickers if t]:
        body = cache.get_or_fetch(
            f"market:earn:{ticker}:{ahead_days}",
            ttl_seconds=cache.ttl_for_kind("events"),
            fetcher=lambda t=ticker: _finnhub_get(
                "/calendar/earnings", {"symbol": t, "from": str(today), "to": str(end)}, api_key
            ),
        )
        out.extend(_upsert_earnings(body.get("earningsCalendar", [])))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/market/tests/test_events_service.py -v`
Expected: the 3 earnings tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/events.py backend/apps/market/tests/test_events_service.py
git commit -m "feat(market): events service — earnings fetch + mock + upsert"
```

---

### Task 3: `events.py` — curated macro + seed fallback

**Files:**
- Create: `backend/apps/market/services/events_seed.py`
- Modify: `backend/apps/market/services/events.py`
- Modify: `backend/apps/market/tests/test_events_service.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/apps/market/tests/test_events_service.py`:

```python
@pytest.mark.django_db
def test_fetch_macro_filters_to_us_high_impact_allowlist():
    body = {"economicCalendar": [
        {"event": "CPI YoY", "country": "US", "impact": "high",
         "time": _soon(5) + " 12:30:00", "estimate": 3.1, "prev": 3.2, "actual": None},
        {"event": "German CPI", "country": "DE", "impact": "high",
         "time": _soon(5) + " 06:00:00"},
        {"event": "Retail Inventories", "country": "US", "impact": "low",
         "time": _soon(6) + " 12:30:00"},
    ]}
    with (
        patch("apps.market.services.events._finnhub_get", return_value=body),
        patch("apps.market.services.events._finnhub_api_key", return_value="k"),
        patch("apps.market.services.events.cache.get_or_fetch",
              side_effect=lambda key, *, ttl_seconds, fetcher: fetcher()),
    ):
        out = events.fetch_macro()
    kinds = {e.kind for e in out}
    assert kinds == {"cpi"}  # German + low-impact dropped


@pytest.mark.django_db
def test_fetch_macro_falls_back_to_seed_when_endpoint_empty():
    seed = [{"event": "FOMC Rate Decision", "country": "US", "impact": "high",
             "time": _soon(7) + " 18:00:00", "estimate": None, "prev": None, "actual": None}]
    with (
        patch("apps.market.services.events._finnhub_api_key", return_value=None),
        patch("apps.market.services.events.SEED_MACRO_EVENTS", seed),
    ):
        out = events.fetch_macro()
    assert len(out) == 1
    assert out[0].kind == "fomc"
    assert out[0].source == "seed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose exec web pytest apps/market/tests/test_events_service.py -k macro -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'fetch_macro'`.

- [ ] **Step 3: Create the seed list + macro half**

Create `backend/apps/market/services/events_seed.py`:

```python
"""Best-effort macro seed used only when Finnhub's economic-calendar is unavailable.

Rows use the SAME shape as Finnhub `/calendar/economic` entries so `_upsert_macro`
handles both. These dates are best-effort and MUST be verified/refreshed against the
official calendars:
  - FOMC:        https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
  - CPI / NFP:   https://www.bls.gov/schedule/news_release/
  - PCE / GDP:   https://www.bea.gov/news/schedule
Keep only high-impact US events. Time is UTC ("YYYY-MM-DD HH:MM:SS").
"""

from __future__ import annotations

# VERIFY these before relying on them in production; the live Finnhub pull upserts over them.
SEED_MACRO_EVENTS: list[dict] = [
    {"event": "FOMC Rate Decision", "country": "US", "impact": "high",
     "time": "2026-06-17 18:00:00", "estimate": None, "prev": None, "actual": None},
    {"event": "CPI YoY", "country": "US", "impact": "high",
     "time": "2026-06-10 12:30:00", "estimate": None, "prev": None, "actual": None},
    {"event": "Nonfarm Payrolls", "country": "US", "impact": "high",
     "time": "2026-06-05 12:30:00", "estimate": None, "prev": None, "actual": None},
]
```

In `backend/apps/market/services/events.py`, add the import near the top:

```python
from apps.market.services.events_seed import SEED_MACRO_EVENTS
```

Append the macro functions:

```python
_MACRO_MAP = [
    ("fomc", "fomc"), ("federal funds", "fomc"), ("interest rate decision", "fomc"),
    ("cpi", "cpi"), ("consumer price", "cpi"),
    ("non-farm", "nfp"), ("nonfarm", "nfp"), ("payroll", "nfp"),
    ("pce", "pce"), ("personal consumption", "pce"),
    ("gdp", "gdp"),
]


def _macro_kind(event_name: str) -> str | None:
    name = (event_name or "").lower()
    for needle, kind in _MACRO_MAP:
        if needle in name:
            return kind
    return None


def _is_high_impact(impact) -> bool:
    return str(impact).lower() in ("high", "3")


def _is_us(country) -> bool:
    return str(country or "").upper() in ("US", "USA", "UNITED STATES")


def _parse_macro_time(t: str) -> datetime | None:
    t = (t or "").strip()
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _upsert_macro(rows: list[dict], *, source: str) -> list[MarketEvent]:
    out: list[MarketEvent] = []
    for r in rows:
        kind = _macro_kind(r.get("event", ""))
        if kind is None or not _is_high_impact(r.get("impact")) or not _is_us(r.get("country")):
            continue
        dt = _parse_macro_time(r.get("time", ""))
        if dt is None:
            continue
        obj, _ = MarketEvent.objects.update_or_create(
            source=source,
            external_id=f"{kind.upper()}:{dt.date().isoformat()}",
            defaults={
                "kind": kind,
                "ticker": "",
                "title": r.get("event") or kind.upper(),
                "event_time": dt,
                "when_hint": "",
                "impact": "high",
                "detail": {"forecast": r.get("estimate"), "prior": r.get("prev"),
                           "actual": r.get("actual")},
            },
        )
        out.append(obj)
    return out


def fetch_macro(*, ahead_days: int = 45) -> list[MarketEvent]:
    """Fetch + upsert curated US high-impact macro. Falls back to SEED_MACRO_EVENTS if empty."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _upsert_macro(SEED_MACRO_EVENTS, source="finnhub")

    api_key = _finnhub_api_key()
    today = datetime.now(UTC).date()
    end = today + timedelta(days=ahead_days)
    rows: list[dict] = []
    if api_key:
        try:
            body = cache.get_or_fetch(
                f"market:macro:{ahead_days}",
                ttl_seconds=cache.ttl_for_kind("events"),
                fetcher=lambda: _finnhub_get(
                    "/calendar/economic", {"from": str(today), "to": str(end)}, api_key
                ),
            )
            rows = body.get("economicCalendar", [])
        except Exception as exc:
            log.warning("market.events.macro_fetch_failed: %s", exc)

    upserted = _upsert_macro(rows, source="finnhub")
    if not upserted:
        upserted = _upsert_macro(SEED_MACRO_EVENTS, source="seed")
    return upserted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/market/tests/test_events_service.py -v`
Expected: all earnings + macro tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/events.py backend/apps/market/services/events_seed.py \
        backend/apps/market/tests/test_events_service.py
git commit -m "feat(market): curated US-macro fetch + seed fallback"
```

---

### Task 4: `events.py` — `upcoming_events` read helper

**Files:**
- Modify: `backend/apps/market/services/events.py`
- Modify: `backend/apps/market/tests/test_events_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/apps/market/tests/test_events_service.py`:

```python
@pytest.mark.django_db
def test_upcoming_events_reads_store_and_computes_days_until():
    from django.utils import timezone
    MarketEvent.objects.create(
        source="finnhub", external_id="EARN:NVDA:x", kind="earnings", ticker="NVDA",
        title="NVDA earnings", event_time=timezone.now() + timedelta(days=3),
        when_hint="amc", impact="high", detail={"eps_est": 0.84},
    )
    MarketEvent.objects.create(
        source="finnhub", external_id="CPI:y", kind="cpi", title="CPI",
        event_time=timezone.now() + timedelta(days=6), impact="high",
    )
    out = events.upcoming_events(["NVDA"], within_days=14)
    assert [e["ticker"] for e in out["earnings"]] == ["NVDA"]
    assert out["earnings"][0]["days_until"] == 3
    assert [m["kind"] for m in out["macro"]] == ["cpi"]


@pytest.mark.django_db
def test_upcoming_events_excludes_macro_when_disabled():
    from django.utils import timezone
    MarketEvent.objects.create(source="s", external_id="CPI:z", kind="cpi", title="CPI",
                               event_time=timezone.now() + timedelta(days=2))
    out = events.upcoming_events([], include_macro=False)
    assert out["macro"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_events_service.py -k upcoming -v`
Expected: FAIL with `AttributeError: ... has no attribute 'upcoming_events'`.

- [ ] **Step 3: Add the read helper**

Append to `backend/apps/market/services/events.py`:

```python
MACRO_KINDS = ["fomc", "cpi", "nfp", "pce", "gdp"]


def _serialize_event(e: MarketEvent, today) -> dict:
    return {
        "kind": e.kind,
        "ticker": e.ticker,
        "title": e.title,
        "event_time": e.event_time.isoformat(),
        "days_until": (e.event_time.date() - today).days,
        "when_hint": e.when_hint,
        "impact": e.impact,
        "detail": e.detail,
    }


def upcoming_events(tickers: list[str], *, within_days: int = 14, include_macro: bool = True) -> dict:
    """Read upcoming events from the store. Best-effort on-demand earnings fill for cold tickers."""
    from django.utils import timezone

    now = timezone.now()
    today = now.date()
    horizon = now + timedelta(days=within_days)
    tickers = [t.upper() for t in tickers if t]

    for t in tickers:
        if not MarketEvent.objects.filter(kind="earnings", ticker=t, event_time__gte=now).exists():
            try:
                fetch_earnings([t])
            except Exception as exc:
                log.warning("market.events.ondemand_fill_failed %s: %s", t, exc)

    earnings_qs = MarketEvent.objects.filter(
        kind="earnings", ticker__in=tickers, event_time__gte=now, event_time__lte=horizon
    ).order_by("event_time")
    earnings = [_serialize_event(e, today) for e in earnings_qs]

    macro = []
    if include_macro:
        macro_qs = MarketEvent.objects.filter(
            kind__in=MACRO_KINDS, event_time__gte=now, event_time__lte=horizon
        ).order_by("event_time")
        macro = [_serialize_event(e, today) for e in macro_qs]

    return {"earnings": earnings, "macro": macro}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/market/tests/test_events_service.py -v`
Expected: all service tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/services/events.py backend/apps/market/tests/test_events_service.py
git commit -m "feat(market): upcoming_events read helper + on-demand fill"
```

---

### Task 5: `market.refresh_events` task + beat schedule

**Files:**
- Modify: `backend/apps/market/tasks.py`
- Modify: `backend/config/celery.py:33-50`
- Create: `backend/apps/market/tests/test_refresh_events_task.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_refresh_events_task.py`:

```python
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.market.tasks import refresh_events
from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.mark.django_db
def test_refresh_events_pulls_watchlist_tickers_and_prunes_old():
    wl = Watchlist.objects.create(name="Core")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="NVDA")
    MarketEvent.objects.create(  # stale → pruned
        source="finnhub", external_id="EARN:OLD:1", kind="earnings", ticker="OLD",
        title="OLD earnings", event_time=timezone.now() - timedelta(days=40),
    )
    with (
        patch("apps.market.tasks.events_service.fetch_earnings", return_value=[1, 2]) as fe,
        patch("apps.market.tasks.events_service.fetch_macro", return_value=[1]) as fm,
    ):
        result = refresh_events()

    fe.assert_called_once()
    assert "NVDA" in fe.call_args.args[0]
    fm.assert_called_once()
    assert result == {"earnings": 2, "macro": 1, "pruned": 1}
    assert not MarketEvent.objects.filter(external_id="EARN:OLD:1").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_refresh_events_task.py -v`
Expected: FAIL with `ImportError: cannot import name 'refresh_events'`.

- [ ] **Step 3: Add the task + beat entry**

Append to `backend/apps/market/tasks.py` (add imports at top with the existing ones):

```python
from datetime import timedelta

from apps.market.models import MarketEvent
from apps.market.services import events as events_service
from apps.profiles.models import WatchlistSymbol


@shared_task(name="market.refresh_events")
def refresh_events() -> dict:
    """Daily refresh of the MarketEvent store for all watchlist tickers + curated macro."""
    tickers = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    n_earn = len(events_service.fetch_earnings(tickers))
    n_macro = len(events_service.fetch_macro())
    cutoff = timezone.now() - timedelta(days=30)
    pruned, _ = MarketEvent.objects.filter(event_time__lt=cutoff).delete()
    return {"earnings": n_earn, "macro": n_macro, "pruned": pruned}
```

In `backend/config/celery.py`, add to `app.conf.beat_schedule` (after the `run-due-postmortems` entry):

```python
    "refresh-market-events-daily": {
        "task": "market.refresh_events",
        "schedule": crontab(hour=9, minute=0),
    },
```

- [ ] **Step 4: Run test + restart workers**

Run: `docker compose exec web pytest apps/market/tests/test_refresh_events_task.py -v`
Expected: PASS.

Then (so the running stack registers the new schedule):
```bash
docker compose restart worker beat
```

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/tasks.py backend/config/celery.py \
        backend/apps/market/tests/test_refresh_events_task.py
git commit -m "feat(market): daily market.refresh_events beat task"
```

---

### Task 6: `days_to_earnings` DSL validation

**Files:**
- Modify: `backend/apps/triggers/dsl.py:13-18,53-72`
- Create: `backend/apps/triggers/tests/test_dsl_days_to_earnings.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/triggers/tests/test_dsl_days_to_earnings.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.triggers.dsl import validate_condition


def test_days_to_earnings_valid():
    validate_condition({"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 2})


def test_days_to_earnings_requires_ticker():
    with pytest.raises(ValidationError):
        validate_condition({"metric": "days_to_earnings", "op": "<=", "value": 2})


def test_days_to_earnings_rejects_crossing_op():
    with pytest.raises(ValidationError):
        validate_condition({"metric": "days_to_earnings", "ticker": "NVDA",
                            "op": "crosses_below", "value": 2})


def test_days_to_earnings_rejects_window():
    with pytest.raises(ValidationError):
        validate_condition({"metric": "days_to_earnings", "ticker": "NVDA",
                            "op": "<=", "value": 2, "window": "1d"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/triggers/tests/test_dsl_days_to_earnings.py -v`
Expected: `test_days_to_earnings_valid` FAILS (`unknown metric`); the crossing test FAILS (no guard yet).

- [ ] **Step 3: Extend the validator**

In `backend/apps/triggers/dsl.py`, update the constants:

```python
VALID_METRICS = {"price", "pct_change", "volume_z", "vix", "position_pl", "position_pl_pct", "days_to_earnings"}
VALID_OPS = {">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"}
VALID_WINDOWS = {"1m", "5m", "15m", "1h", "1d"}
TICKER_REQUIRED = {"price", "pct_change", "volume_z", "days_to_earnings"}
WINDOW_REQUIRED = {"pct_change", "volume_z"}
NON_CROSSING_METRICS = {"days_to_earnings"}
LEAF_KEYS = {"metric", "ticker", "op", "value", "window"}
```

In `validate_condition`, after the `op` validation block (right after the `value` number check), add:

```python
    if metric in NON_CROSSING_METRICS and op in ("crosses_above", "crosses_below"):
        raise ValidationError(f"{path}.op: crossing ops not supported for metric {metric!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec web pytest apps/triggers/tests/test_dsl_days_to_earnings.py -v`
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/triggers/dsl.py backend/apps/triggers/tests/test_dsl_days_to_earnings.py
git commit -m "feat(triggers): validate days_to_earnings leaf (comparison ops only)"
```

---

### Task 7: `days_to_earnings` evaluation (leaf_key + metrics + describe)

**Files:**
- Modify: `backend/apps/triggers/evaluator.py:43-54`
- Modify: `backend/apps/triggers/metrics.py`
- Modify: `backend/apps/triggers/services/describe.py:15-33`
- Create: `backend/apps/triggers/tests/test_metrics_days_to_earnings.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/triggers/tests/test_metrics_days_to_earnings.py`:

```python
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.triggers.evaluator import evaluate, leaf_key
from apps.triggers.metrics import build_snapshot
from apps.triggers.services.describe import describe


def test_leaf_key_for_days_to_earnings():
    assert leaf_key({"metric": "days_to_earnings", "ticker": "NVDA"}) == "days_to_earnings:NVDA"


@pytest.mark.django_db
def test_build_snapshot_resolves_days_to_earnings():
    MarketEvent.objects.create(
        source="finnhub", external_id="EARN:NVDA:x", kind="earnings", ticker="NVDA",
        title="NVDA earnings", event_time=timezone.now() + timedelta(days=3),
    )
    cond = {"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 5}
    snap = build_snapshot([SimpleNamespace(condition=cond)])
    assert snap["days_to_earnings:NVDA"] == 3
    assert evaluate(cond, snap)[0] is True


@pytest.mark.django_db
def test_build_snapshot_days_to_earnings_unknown_is_none():
    cond = {"metric": "days_to_earnings", "ticker": "ZZZZ", "op": "<=", "value": 5}
    with pytest.MonkeyPatch.context() as mp:
        # Block the on-demand fill from hitting Finnhub.
        from apps.market.services import events
        mp.setattr(events, "fetch_earnings", lambda *a, **k: [])
        snap = build_snapshot([SimpleNamespace(condition=cond)])
    assert snap["days_to_earnings:ZZZZ"] is None
    assert evaluate(cond, snap)[0] is False


def test_describe_days_to_earnings():
    assert describe({"days_to_earnings:NVDA": 2}) == "NVDA earnings in 2d"
```

> Note: `build_snapshot` only calls `fetch_quotes` when a price/pct_change/volume_z/vix leaf is present, so a pure `days_to_earnings` snapshot performs no Schwab I/O. It does touch Redis (`trigger:last_tick_at`), which is available in the `web` container.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/triggers/tests/test_metrics_days_to_earnings.py -v`
Expected: `test_leaf_key_for_days_to_earnings` FAILS (returns `price:NVDA`); the build_snapshot tests FAIL (KeyError / None).

- [ ] **Step 3a: Add the `leaf_key` branch**

In `backend/apps/triggers/evaluator.py`, inside `leaf_key`, add **before** the `# price` fallback:

```python
    if metric == "days_to_earnings":
        return f"days_to_earnings:{node['ticker']}"
    # price
    return f"price:{node['ticker']}"
```

- [ ] **Step 3b: Resolve the metric in `build_snapshot`**

In `backend/apps/triggers/metrics.py`, add a helper near the other private helpers:

```python
def _earnings_days_map(leaves: list[dict]) -> dict[str, int]:
    """Soonest upcoming-earnings countdown (in days) per ticker, batched into one query."""
    from apps.market.models import MarketEvent
    from django.utils import timezone

    tickers = {leaf["ticker"].upper() for leaf in leaves
               if leaf["metric"] == "days_to_earnings" and leaf.get("ticker")}
    if not tickers:
        return {}
    now = timezone.now()
    today = now.date()
    rows = (MarketEvent.objects
            .filter(kind="earnings", ticker__in=tickers, event_time__gte=now)
            .order_by("ticker", "event_time"))
    out: dict[str, int] = {}
    for r in rows:
        if r.ticker not in out:  # first row per ticker is the soonest
            out[r.ticker] = (r.event_time.date() - today).days
    return out
```

Then in `build_snapshot`, after the existing `has_vix = ...` line (before the per-leaf loop), add:

```python
    earnings_days = _earnings_days_map(leaves)
```

And inside the per-leaf `for leaf in leaves:` loop, add a branch alongside the others:

```python
        elif metric == "days_to_earnings":
            assert ticker is not None
            snapshot[key] = earnings_days.get(ticker.upper())
```

- [ ] **Step 3c: Add the describe phrasing**

In `backend/apps/triggers/services/describe.py`, inside `_format_one`, add before the final `return`:

```python
    if key.startswith("days_to_earnings:"):
        _, ticker = key.split(":", 1)
        return f"{ticker} earnings in {int(value)}d"
    return f"{key}={value}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/triggers/tests/test_metrics_days_to_earnings.py -v`
Expected: all 4 PASS. Also run the full triggers suite to catch regressions:
`docker compose exec web pytest apps/triggers -v`

- [ ] **Step 5: Commit**

```bash
git add backend/apps/triggers/evaluator.py backend/apps/triggers/metrics.py \
        backend/apps/triggers/services/describe.py \
        backend/apps/triggers/tests/test_metrics_days_to_earnings.py
git commit -m "feat(triggers): resolve + describe days_to_earnings metric"
```

---

### Task 8: Opt-in `"events"` snapshot section

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py:1-21,92-116`
- Modify: `backend/apps/snapshots/serializer.py:77-95,286-296`
- Create: `backend/apps/snapshots/tests/test_events_section.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/snapshots/tests/test_events_section.py`:

```python
from apps.snapshots.serializer import _render_events, _title


def test_events_title():
    assert _title("events") == "Upcoming events"


def test_render_events_lists_earnings_and_macro():
    payload = {
        "earnings": [{"ticker": "NVDA", "days_until": 2, "when_hint": "amc",
                      "detail": {"eps_est": 0.84}}],
        "macro": [{"title": "CPI", "days_until": 5}],
    }
    out = _render_events(payload)
    assert "NVDA earnings in 2d" in out
    assert "AMC" in out
    assert "est EPS 0.84" in out
    assert "CPI in 5d" in out


def test_render_events_empty():
    assert "_(none" in _render_events({"earnings": [], "macro": []})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/snapshots/tests/test_events_section.py -v`
Expected: FAIL with `ImportError: cannot import name '_render_events'`.

- [ ] **Step 3a: Add the capture fetcher**

In `backend/apps/snapshots/services/__init__.py`, add the import alongside the other service imports (after the `fetch_news` import):

```python
from apps.market.services.events import upcoming_events
```

Add to the `_FETCHERS` dict (e.g. after the `"chain"` entry):

```python
    "events": lambda *, watchlist_tickers, **_: {
        "data": upcoming_events(list(watchlist_tickers), within_days=14, include_macro=True),
    },
```

- [ ] **Step 3b: Add the renderer + title**

In `backend/apps/snapshots/serializer.py`, add `"events"` to the `_title` dict:

```python
        "image": "Chart image",
        "events": "Upcoming events",
```

Add the renderer function (near the other `_render_*` functions):

```python
def _render_events(payload) -> str:
    earnings = payload.get("earnings", []) if isinstance(payload, dict) else []
    macro = payload.get("macro", []) if isinstance(payload, dict) else []
    if not earnings and not macro:
        return "## Upcoming events\n_(none in the next 14 days)_"
    lines = ["## Upcoming events"]
    for e in earnings:
        hint = f", {e['when_hint'].upper()}" if e.get("when_hint") else ""
        est = (e.get("detail") or {}).get("eps_est")
        est_s = f", est EPS {est}" if est is not None else ""
        lines.append(f"- {e['ticker']} earnings in {e['days_until']}d{hint}{est_s}")
    for m in macro:
        lines.append(f"- {m['title']} in {m['days_until']}d")
    return "\n".join(lines)
```

Register it in the `_RENDERERS` dict:

```python
    "image": _render_image,
    "events": _render_events,
    "notes": lambda _p: "",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/snapshots/tests/test_events_section.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/serializer.py \
        backend/apps/snapshots/tests/test_events_section.py
git commit -m "feat(snapshots): opt-in events section (capture + AI render)"
```

---

### Task 9: `GET /api/market/events/` endpoint

**Files:**
- Modify: `backend/apps/market/views.py:14-18,86-93`
- Modify: `backend/apps/market/urls.py:11-20`
- Create: `backend/apps/market/tests/test_events_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `backend/apps/market/tests/test_events_endpoint.py`:

```python
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent


@pytest.fixture
def api():
    from rest_framework.test import APIClient
    return APIClient()


@pytest.mark.django_db
def test_events_endpoint_returns_upcoming(api):
    MarketEvent.objects.create(
        source="finnhub", external_id="EARN:NVDA:x", kind="earnings", ticker="NVDA",
        title="NVDA earnings", event_time=timezone.now() + timedelta(days=3),
    )
    r = api.get("/api/market/events/?tickers=NVDA&within_days=14")
    assert r.status_code == 200
    body = r.json()
    assert body["earnings"][0]["ticker"] == "NVDA"
    assert "macro" in body


@pytest.mark.django_db
def test_events_endpoint_macro_toggle(api):
    MarketEvent.objects.create(source="s", external_id="CPI:z", kind="cpi", title="CPI",
                               event_time=timezone.now() + timedelta(days=2))
    r = api.get("/api/market/events/?include_macro=false")
    assert r.json()["macro"] == []


@pytest.mark.django_db
def test_events_endpoint_invalid_within_days(api):
    r = api.get("/api/market/events/?within_days=abc")
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec web pytest apps/market/tests/test_events_endpoint.py -v`
Expected: FAIL with 404 (route not registered).

- [ ] **Step 3: Add the view + route**

In `backend/apps/market/views.py`, add the import (with the other service imports):

```python
from apps.market.services.events import upcoming_events
```

Add the view (e.g. after `news`):

```python
@require_GET
def events(request: HttpRequest) -> JsonResponse:
    raw = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw.split(",") if t.strip()]
    try:
        within = int(request.GET.get("within_days", "14"))
    except ValueError:
        return _err("invalid_within_days", "within_days must be an integer", 400)
    include_macro = request.GET.get("include_macro", "true").lower() != "false"
    return JsonResponse(upcoming_events(tickers, within_days=within, include_macro=include_macro))
```

In `backend/apps/market/urls.py`, add to `urlpatterns` (after the `news/` line):

```python
    path("events/", views.events, name="events"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose exec web pytest apps/market/tests/test_events_endpoint.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/apps/market/views.py backend/apps/market/urls.py \
        backend/apps/market/tests/test_events_endpoint.py
git commit -m "feat(market): GET /api/market/events/ endpoint"
```

---

### Task 10: Frontend client + `useUpcomingEvents` hook

**Files:**
- Modify: `frontend/src/api/market.ts`
- Create: `frontend/src/hooks/useUpcomingEvents.ts`
- Create: `frontend/src/__tests__/hooks/useUpcomingEvents.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/hooks/useUpcomingEvents.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "@/api/market";
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useUpcomingEvents", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("fetches upcoming events for the given tickers", async () => {
    const spy = vi.spyOn(api, "fetchUpcomingEvents").mockResolvedValue({
      earnings: [{ kind: "earnings", ticker: "NVDA", title: "NVDA earnings",
        event_time: "2026-05-29T21:00:00Z", days_until: 2, when_hint: "amc",
        impact: "high", detail: {} }],
      macro: [],
    });
    const { result } = renderHook(() => useUpcomingEvents(["NVDA"]), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.earnings[0].ticker).toBe("NVDA");
    expect(spy).toHaveBeenCalledWith(["NVDA"], 14);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/hooks/useUpcomingEvents.test.tsx`
Expected: FAIL (`fetchUpcomingEvents` / `useUpcomingEvents` not exported).

- [ ] **Step 3: Add the client fn + hook**

Append to `frontend/src/api/market.ts`:

```ts
export type MarketEvent = {
  kind: string;
  ticker: string;
  title: string;
  event_time: string;
  days_until: number;
  when_hint: string;
  impact: string;
  detail: Record<string, unknown>;
};

export type UpcomingEvents = { earnings: MarketEvent[]; macro: MarketEvent[] };

export const fetchUpcomingEvents = (tickers: string[] = [], withinDays = 14, includeMacro = true) => {
  const params = new URLSearchParams();
  if (tickers.length) params.set("tickers", tickers.join(","));
  params.set("within_days", String(withinDays));
  params.set("include_macro", String(includeMacro));
  return apiGet<UpcomingEvents>(`/api/market/events/?${params.toString()}`);
};
```

Create `frontend/src/hooks/useUpcomingEvents.ts`:

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchUpcomingEvents } from "@/api/market";

export const useUpcomingEvents = (tickers: string[] = [], withinDays = 14) =>
  useQuery({
    queryKey: ["upcoming-events", tickers, withinDays],
    queryFn: () => fetchUpcomingEvents(tickers, withinDays),
    refetchInterval: 300_000,
  });
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/hooks/useUpcomingEvents.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/market.ts frontend/src/hooks/useUpcomingEvents.ts \
        frontend/src/__tests__/hooks/useUpcomingEvents.test.tsx
git commit -m "feat(frontend): market events client + useUpcomingEvents hook"
```

---

### Task 11: `/events` page + route + nav + command + shortcut

**Files:**
- Create: `frontend/src/pages/EventsPage.tsx`
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/layout/SideNav.tsx:4-8`
- Modify: `frontend/src/components/layout/AppLayout.tsx:34-35`
- Modify: `frontend/src/hooks/useKeyboardShortcuts.ts:17-26`

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/EventsPage.tsx`:

```tsx
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";
import { useWatchlists } from "@/hooks/useWatchlists";
import { Skeleton } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import type { MarketEvent } from "@/api/market";

function EventRow({ e }: { e: MarketEvent }) {
  const eps = (e.detail as { eps_est?: number } | null)?.eps_est;
  return (
    <li className="flex items-baseline justify-between border-b border-rule py-2">
      <span className="font-medium">
        {e.ticker ? `${e.ticker} earnings` : e.title}
        {e.when_hint ? ` (${e.when_hint.toUpperCase()})` : ""}
      </span>
      <span className="text-sm text-muted">
        in {e.days_until}d{eps != null ? ` · est EPS ${eps}` : ""}
      </span>
    </li>
  );
}

export default function EventsPage() {
  const { data: watchlists } = useWatchlists();
  const tickers = (watchlists ?? []).flatMap((w) => w.symbols.map((s) => s.ticker));
  const { data, isLoading } = useUpcomingEvents(tickers, 30);

  if (isLoading) return <Skeleton className="h-40" />;

  const earnings = data?.earnings ?? [];
  const macro = data?.macro ?? [];

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-lg font-semibold">Upcoming earnings</h2>
        {earnings.length === 0 ? (
          <EmptyState title="No upcoming earnings" body="Across your watchlists in the next 30 days." />
        ) : (
          <ul>{earnings.map((e) => <EventRow key={`${e.ticker}-${e.event_time}`} e={e} />)}</ul>
        )}
      </section>
      <section>
        <h2 className="mb-3 text-lg font-semibold">Macro calendar</h2>
        {macro.length === 0 ? (
          <EmptyState title="No macro events" body="No high-impact US events in the next 30 days." />
        ) : (
          <ul>{macro.map((m) => <EventRow key={`${m.kind}-${m.event_time}`} e={m} />)}</ul>
        )}
      </section>
    </div>
  );
}
```

> **Verify imports against the real files before trusting them** (tsc will flag mismatches): the named-vs-default export style of `Skeleton`, `EmptyState`, and `useWatchlists`, and the watchlist item shape. If `useWatchlists`'s item type names the symbols field differently than `symbols`/`ticker`, match the actual type (see `frontend/src/hooks/useWatchlists.ts` + `frontend/src/api`) — the DRF→TS key convention means a wrong key silently reads `undefined`. Mirror a sibling page that already uses these primitives (e.g. `AnalyticsPage.tsx`/`ThesesPage.tsx`) for the exact import lines and Tailwind token classes (`text-muted`, `border-rule`, `text-fg`).

- [ ] **Step 2: Wire route + nav + command + shortcut**

In `frontend/src/router.tsx`, add the import next to the other page imports:

```tsx
import EventsPage from "./pages/EventsPage";
```

Add the route as a child of the `<AppLayout>` route (after the `triggers` routes, before `analytics`):

```tsx
      { path: "events", element: <EventsPage />, handle: { crumb: "Events" } },
```

In `frontend/src/components/layout/SideNav.tsx`, add to the `TRADING` array:

```tsx
const TRADING: Array<[string, string, string]> = [
  ["/theses", "Theses", "TH"],
  ["/events", "Events", "EV"],
  ["/profiles", "Profiles", "PR"],
  ["/watchlists", "Watchlists", "WL"],
];
```

In `frontend/src/components/layout/AppLayout.tsx`, add to the commands array in `useDefaultCommands` (after the `go-theses` entry):

```tsx
      { id: "go-events", label: "Go to Events", keywords: "earnings calendar fomc cpi macro",
        run: () => nav("/events") },
```

In `frontend/src/hooks/useKeyboardShortcuts.ts`, add to the `SHORTCUTS` map:

```ts
  j: { path: "/theses", label: "Theses" },
  e: { path: "/events", label: "Events" },
```

- [ ] **Step 3: Verify build + lint**

Run:
```bash
docker compose exec frontend pnpm exec tsc --noEmit
docker compose exec frontend pnpm run lint
```
Expected: no type errors, lint clean. (If `tsc` flags the watchlist symbol shape, fix the field names per the note above.)

- [ ] **Step 4: Smoke-test the route in the app**

With `make dev` running, open `http://127.0.0.1:5173/events` and confirm the page renders (earnings + macro sections, empty states when no data). Confirm `g e` navigates there and the Events nav link works.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/EventsPage.tsx frontend/src/router.tsx \
        frontend/src/components/layout/SideNav.tsx frontend/src/components/layout/AppLayout.tsx \
        frontend/src/hooks/useKeyboardShortcuts.ts
git commit -m "feat(frontend): /events page + nav + command + g e shortcut"
```

---

### Task 12: `<UpcomingEvents>` dashboard badge

**Files:**
- Create: `frontend/src/components/UpcomingEvents.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/UpcomingEvents.tsx`:

```tsx
import { Link } from "react-router-dom";
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";

export default function UpcomingEvents({ tickers = [] }: { tickers?: string[] }) {
  const { data } = useUpcomingEvents(tickers, 7);
  const items = [...(data?.earnings ?? []), ...(data?.macro ?? [])]
    .sort((a, b) => a.days_until - b.days_until)
    .slice(0, 2);
  if (items.length === 0) return null;
  return (
    <div className="flex items-center gap-2 text-sm">
      {items.map((e) => (
        <Link
          key={`${e.kind}-${e.ticker}-${e.event_time}`}
          to="/events"
          className="rounded border border-rule px-2 py-1 text-muted hover:text-fg"
        >
          {e.ticker ? `${e.ticker} earnings` : e.title} · {e.days_until}d
        </Link>
      ))}
    </div>
  );
}
```

> Match the existing token/utility class names used by neighboring Dashboard components (`text-muted`, `border-rule`, etc. come from the project's Tailwind theme; adjust if a class doesn't exist).

- [ ] **Step 2: Mount on the Dashboard**

In `frontend/src/pages/Dashboard.tsx`, add the import:

```tsx
import UpcomingEvents from "@/components/UpcomingEvents";
```

Render it near the top of the dashboard (pass the active watchlist tickers if the Dashboard already has them in scope; otherwise `<UpcomingEvents />` shows macro-only since earnings need tickers). Example, inside the dashboard header area:

```tsx
<UpcomingEvents tickers={watchlistTickers} />
```

If the Dashboard does not already compute `watchlistTickers`, use `<UpcomingEvents />` (macro-only) for v1 — earnings still surface on `/events`.

- [ ] **Step 3: Verify build + lint**

Run:
```bash
docker compose exec frontend pnpm exec tsc --noEmit
docker compose exec frontend pnpm run lint
```
Expected: clean.

- [ ] **Step 4: Smoke-test on the Dashboard**

With `make dev` running, open `http://127.0.0.1:5173/` and confirm the chip strip renders (or is absent when there are no events within 7 days), and that clicking a chip navigates to `/events`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UpcomingEvents.tsx frontend/src/pages/Dashboard.tsx
git commit -m "feat(frontend): upcoming-events dashboard badge"
```

---

### Task 13: Full check + docs note

**Files:**
- Modify: `CLAUDE.md` (Non-obvious conventions)
- Modify: `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` (milestone pointer)

- [ ] **Step 1: Run the full check**

Run: `make check`
Expected: ruff + pytest + frontend eslint/tsc/vitest all green. Fix any regressions before proceeding.

- [ ] **Step 2: Add a CLAUDE.md convention note**

Under "Non-obvious conventions" in `CLAUDE.md`, add a bullet:

```markdown
- **Market events are a forward calendar, not a session calendar.** `apps.market.MarketEvent` (earnings + curated US macro) is distinct from `apps.market.calendar` (trading sessions). Earnings/macro come from Finnhub via `apps/market/services/events.py` (cloned from `news.py`), refreshed daily by `market.refresh_events` (beat). Reads go through `events.upcoming_events(...)` — used by the `days_to_earnings` trigger leaf, the opt-in `"events"` snapshot section, and `GET /api/market/events/`. Macro degrades to `SEED_MACRO_EVENTS` when Finnhub's economic-calendar isn't available.
```

- [ ] **Step 3: Update the milestone pointer**

In `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`, under "Future (not yet in flight):", add:

```markdown
- **Market events**: `MarketEvent` store (earnings + curated US macro) → `days_to_earnings` trigger leaf, opt-in `"events"` snapshot section, `/events` page. Foundation for the Morning Briefing. Spec: `docs/superpowers/specs/2026-05-27-market-events-design.md`; plan: `docs/superpowers/plans/2026-05-27-market-events.md`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-04-16-ai-dashboard-design.md
git commit -m "docs: record market-events convention + milestone pointer"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- Data model → Task 1. Service (earnings/macro/seed/mock/cache) → Tasks 2–4. Refresh task + beat → Task 5. `days_to_earnings` (DSL/evaluator/metrics/describe) → Tasks 6–7. AI `"events"` section → Task 8. API → Task 9. Frontend client/hook/page/nav/command/shortcut/badge → Tasks 10–12. Ops/docs → Task 13.
- Spec "out of scope" items (corporate actions, non-US macro, surprise triggers, generalized countdown) have no tasks — correct.

**2. Placeholder scan** — no "TBD"/"add error handling"/"similar to Task N". The `SEED_MACRO_EVENTS` dates are real seed data with an explicit verification note + official sources (inherent maintained reference data, not a code placeholder); tests monkeypatch the list so they are date-stable.

**3. Type/name consistency** — verified across tasks:
- `MarketEvent` fields (`source, external_id, kind, ticker, title, event_time, when_hint, impact, detail`) used identically in model, service, task, metrics, endpoint, and tests.
- Service surface: `fetch_earnings`, `fetch_macro`, `upcoming_events`, `_upsert_earnings`, `_upsert_macro`, `_finnhub_get`, `_finnhub_api_key`, `SEED_MACRO_EVENTS`, `MACRO_KINDS` — defined in Tasks 2–4, referenced consistently in Tasks 5/8/9.
- Leaf key string `days_to_earnings:<ticker>` consistent between `evaluator.leaf_key` (Task 7a), `metrics` set (7b), and `describe` (7c).
- Frontend: `fetchUpcomingEvents(tickers, withinDays, includeMacro)` + `UpcomingEvents`/`MarketEvent` types consistent across `api/market.ts` (Task 10), hook (10), page (11), badge (12). The hook test asserts `fetchUpcomingEvents(["NVDA"], 14)` — matches the hook's 2-arg call.

**Known follow-up flagged in-plan:** the `EventsPage`/badge assume `useWatchlists()` items expose `symbols[].ticker`; Task 11/12 notes instruct matching the actual TS shape if it differs (tsc will catch it).
