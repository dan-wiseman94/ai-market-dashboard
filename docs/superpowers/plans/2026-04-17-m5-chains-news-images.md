# M5 — Option Chains + News + Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add option chains, financial news, client-captured screenshots, and Playwright-rendered chart PNGs to the snapshot pipeline. Build the `/market/:ticker` page that consumes the new data live and the `/render/chart` deterministic chart route Playwright drives.

**Architecture:** New per-fetch JSONB row for chains (`OptionChainSnapshot`), per-article rows for news (`NewsItem` keyed on `(provider, external_id)`), and inline `BinaryField` for images (`SnapshotImage`). Three new fetchers slot into the existing `_FETCHERS` dict in `apps/snapshots/services.py`; the file is reorganized into a package. Worker container gets a `worker-base` Dockerfile target with chromium for Playwright. Frontend gains a `Chart` component (lightweight-charts), a `ChartCaptureButton` (html2canvas → upload), a deterministic `/render/chart` route, and a per-ticker `/market/:ticker` page combining chart + chain table + news feed.

**Tech Stack:** Django 5 + DRF + Channels, Celery, Postgres 16, Redis, Playwright (chromium) in worker container, React 18 + Vite + TanStack Query + lightweight-charts + html2canvas + react-router-dom, Finnhub HTTP API for news.

**Spec:** `docs/superpowers/specs/2026-04-17-m5-chains-news-images-design.md`

**Scope note on AI integration:** `serialize_for_ai` and `build_image_blocks` are currently consumed only by tests; no thread-send/AI-run code path consumes them yet (carry-over from M3/M4). M5 builds and tests these helpers with the same coverage pattern; wiring snapshot serialization into the actual AI provider call is its own concern affecting all section types and is deferred to a later milestone.

---

## Task 1: `OptionChainSnapshot` model + migration

**Files:**
- Modify: `backend/apps/market/models.py` (add new model at end)
- Test: `backend/apps/market/tests/test_chain_model.py` (new)
- Migration: auto-generated `backend/apps/market/migrations/00XX_optionchainsnapshot.py`

- [ ] **Step 1.1: Write the failing test**

`backend/apps/market/tests/test_chain_model.py`:
```python
import pytest
from apps.market.models import OptionChainSnapshot


@pytest.mark.django_db
def test_optionchainsnapshot_persists_payload_and_expiries():
    row = OptionChainSnapshot.objects.create(
        ticker="SPY",
        expiries=["2026-04-25", "2026-05-16"],
        payload={
            "underlying_last": "521.30",
            "expiries": {"2026-04-25": {"calls": [], "puts": []}},
        },
    )
    fetched = OptionChainSnapshot.objects.get(id=row.id)
    assert fetched.ticker == "SPY"
    assert fetched.expiries == ["2026-04-25", "2026-05-16"]
    assert fetched.payload["underlying_last"] == "521.30"
    assert fetched.fetched_at is not None
```

- [ ] **Step 1.2: Run the test to verify it fails**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_model.py -v
```
Expected: ERROR or `AttributeError: module 'apps.market.models' has no attribute 'OptionChainSnapshot'`.

- [ ] **Step 1.3: Add the model**

Append to `backend/apps/market/models.py`:
```python
class OptionChainSnapshot(models.Model):
    """One row per fetch of an option chain. Full chain in JSONB."""

    ticker = models.CharField(max_length=16, db_index=True)
    expiries = models.JSONField(default=list)
    payload = models.JSONField()
    fetched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes: ClassVar = [models.Index(fields=["ticker", "-fetched_at"])]

    def __str__(self) -> str:
        return f"OptionChainSnapshot({self.ticker}, {self.fetched_at})"
```

- [ ] **Step 1.4: Generate + apply migration**

```bash
docker compose exec web python manage.py makemigrations market
docker compose exec web python manage.py migrate market
```
Expected: a new migration file created, applied without error.

- [ ] **Step 1.5: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_model.py -v
```
Expected: 1 passed.

- [ ] **Step 1.6: Commit**

```bash
git add backend/apps/market/models.py backend/apps/market/migrations/ backend/apps/market/tests/test_chain_model.py
git commit -m "feat(market): OptionChainSnapshot model (per-fetch JSONB blob)"
```

---

## Task 2: `NewsItem` model + migration

**Files:**
- Modify: `backend/apps/market/models.py`
- Test: `backend/apps/market/tests/test_news_model.py` (new)
- Migration: auto-generated

- [ ] **Step 2.1: Write the failing test**

`backend/apps/market/tests/test_news_model.py`:
```python
from datetime import datetime, timezone

import pytest
from django.db import IntegrityError
from apps.market.models import NewsItem


@pytest.mark.django_db
def test_newsitem_unique_per_provider_external_id():
    NewsItem.objects.create(
        provider="finnhub", external_id="abc123",
        ticker="SPY", headline="Fed minutes", url="https://example.com/1",
        source="Reuters",
        published_at=datetime(2026, 4, 17, 9, 12, tzinfo=timezone.utc),
    )
    with pytest.raises(IntegrityError):
        NewsItem.objects.create(
            provider="finnhub", external_id="abc123",
            ticker="SPY", headline="dup", url="https://example.com/1",
            source="Reuters",
            published_at=datetime(2026, 4, 17, 9, 12, tzinfo=timezone.utc),
        )


@pytest.mark.django_db
def test_newsitem_blank_ticker_for_market_wide_news():
    n = NewsItem.objects.create(
        provider="finnhub", external_id="market1",
        ticker="", headline="Market-wide", url="https://example.com/m",
        source="Bloomberg",
        published_at=datetime(2026, 4, 17, 8, 0, tzinfo=timezone.utc),
    )
    assert n.ticker == ""
```

- [ ] **Step 2.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/market/tests/test_news_model.py -v
```
Expected: ERROR — `NewsItem` not defined.

- [ ] **Step 2.3: Add the model**

Append to `backend/apps/market/models.py`:
```python
class NewsItem(models.Model):
    """One row per news article. Deduplicated on (provider, external_id)."""

    provider = models.CharField(max_length=16)
    external_id = models.CharField(max_length=64, db_index=True)
    ticker = models.CharField(max_length=16, db_index=True, blank=True, default="")
    headline = models.CharField(max_length=512)
    summary = models.TextField(blank=True, default="")
    url = models.URLField(max_length=1024)
    source = models.CharField(max_length=64, blank=True, default="")
    published_at = models.DateTimeField(db_index=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["provider", "external_id"], name="uniq_news_provider_id",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["ticker", "-published_at"])]

    def __str__(self) -> str:
        return f"NewsItem({self.provider}/{self.external_id})"
```

- [ ] **Step 2.4: Generate + apply migration**

```bash
docker compose exec web python manage.py makemigrations market
docker compose exec web python manage.py migrate market
```

- [ ] **Step 2.5: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_news_model.py -v
```
Expected: 2 passed.

- [ ] **Step 2.6: Commit**

```bash
git add backend/apps/market/models.py backend/apps/market/migrations/ backend/apps/market/tests/test_news_model.py
git commit -m "feat(market): NewsItem model (provider+external_id dedup)"
```

---

## Task 3: `SnapshotImage` model + migration

**Files:**
- Modify: `backend/apps/snapshots/models.py`
- Test: `backend/apps/snapshots/tests/test_image_model.py` (new)
- Migration: auto-generated

- [ ] **Step 3.1: Write the failing test**

`backend/apps/snapshots/tests/test_image_model.py`:
```python
import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # minimal valid PNG header


@pytest.mark.django_db
def test_snapshotimage_attached_to_snapshot():
    profile = TradingProfile.objects.create(name="Default", style_text="x")
    snap = Snapshot.objects.create(profile=profile, includes=["image"])
    img = SnapshotImage.objects.create(
        snapshot=snap, kind="client_capture", data=PNG_BYTES, caption="SPY 5m",
    )
    assert img.id is not None
    assert bytes(img.data).startswith(b"\x89PNG")
    assert img.snapshot_id == snap.id


@pytest.mark.django_db
def test_snapshotimage_can_be_staged_without_snapshot():
    img = SnapshotImage.objects.create(
        snapshot=None, kind="client_capture", data=PNG_BYTES,
    )
    assert img.snapshot is None
```

- [ ] **Step 3.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_image_model.py -v
```
Expected: ERROR — `SnapshotImage` not defined.

- [ ] **Step 3.3: Add the model**

Append to `backend/apps/snapshots/models.py`:
```python
class SnapshotImage(models.Model):
    KIND_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("client_capture", "Client capture"),
        ("server_render", "Server render"),
    ]

    snapshot = models.ForeignKey(
        Snapshot, on_delete=models.CASCADE, related_name="images",
        null=True, blank=True,
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    data = models.BinaryField()
    mime_type = models.CharField(max_length=32, default="image/png")
    caption = models.CharField(max_length=256, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self) -> str:
        return f"SnapshotImage({self.id}, {self.kind})"
```

- [ ] **Step 3.4: Generate + apply migration**

```bash
docker compose exec web python manage.py makemigrations snapshots
docker compose exec web python manage.py migrate snapshots
```

- [ ] **Step 3.5: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_image_model.py -v
```
Expected: 2 passed.

- [ ] **Step 3.6: Commit**

```bash
git add backend/apps/snapshots/models.py backend/apps/snapshots/migrations/ backend/apps/snapshots/tests/test_image_model.py
git commit -m "feat(snapshots): SnapshotImage model (BinaryField, nullable snapshot FK for staging)"
```

---

## Task 4: Chain normalizer (pure function) + tests

**Files:**
- Create: `backend/apps/market/services/chain.py`
- Test: `backend/apps/market/tests/test_chain_normalize.py`

- [ ] **Step 4.1: Write the failing test**

`backend/apps/market/tests/test_chain_normalize.py`:
```python
from apps.market.services.chain import _normalize_chain


SCHWAB_RESPONSE = {
    "underlyingPrice": 521.30,
    "callExpDateMap": {
        "2026-04-25:8": {
            "515.0": [{
                "strikePrice": 515.0, "bid": 7.20, "ask": 7.30, "last": 7.25,
                "totalVolume": 1234, "openInterest": 5678,
                "delta": 0.72, "gamma": 0.04, "theta": -0.12, "vega": 0.18,
                "volatility": 18.4,
            }],
            "520.0": [{
                "strikePrice": 520.0, "bid": 3.85, "ask": 3.95, "last": 3.90,
                "totalVolume": 999, "openInterest": 1111,
                "delta": 0.55, "gamma": 0.05, "theta": -0.13, "vega": 0.20,
                "volatility": 17.9,
            }],
        },
    },
    "putExpDateMap": {
        "2026-04-25:8": {
            "515.0": [{
                "strikePrice": 515.0, "bid": 0.95, "ask": 1.00, "last": 0.97,
                "totalVolume": 222, "openInterest": 4444,
                "delta": -0.28, "gamma": 0.04, "theta": -0.10, "vega": 0.18,
                "volatility": 19.1,
            }],
        },
    },
}


def test_normalize_chain_flattens_schwab_shape():
    out = _normalize_chain(SCHWAB_RESPONSE)
    assert out["underlying_last"] == "521.30"
    assert "2026-04-25" in out["expiries"]
    calls = out["expiries"]["2026-04-25"]["calls"]
    assert len(calls) == 2
    assert calls[0]["strike"] == "515.00"
    assert calls[0]["bid"] == "7.20"
    assert calls[0]["delta"] == "0.72"
    puts = out["expiries"]["2026-04-25"]["puts"]
    assert len(puts) == 1
    assert puts[0]["strike"] == "515.00"


def test_normalize_chain_handles_empty_maps():
    out = _normalize_chain({"underlyingPrice": 100.0, "callExpDateMap": {}, "putExpDateMap": {}})
    assert out["underlying_last"] == "100.00"
    assert out["expiries"] == {}
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_normalize.py -v
```
Expected: ERROR — `chain.py` doesn't exist.

- [ ] **Step 4.3: Implement `_normalize_chain`**

`backend/apps/market/services/chain.py`:
```python
"""Option chain fetching, normalization, and caching."""
from __future__ import annotations


def _fmt(x) -> str | None:
    if x is None:
        return None
    return f"{float(x):.2f}"


def _normalize_contract(c: dict) -> dict:
    return {
        "strike": _fmt(c.get("strikePrice")),
        "bid": _fmt(c.get("bid")),
        "ask": _fmt(c.get("ask")),
        "last": _fmt(c.get("last")),
        "volume": c.get("totalVolume"),
        "oi": c.get("openInterest"),
        "delta": _fmt(c.get("delta")),
        "gamma": _fmt(c.get("gamma")),
        "theta": _fmt(c.get("theta")),
        "vega": _fmt(c.get("vega")),
        "iv": _fmt(c.get("volatility")),
    }


def _flatten_side(exp_date_map: dict) -> dict[str, list[dict]]:
    """Flatten Schwab's nested {"YYYY-MM-DD:DTE": {"strike": [contract]}} → {"YYYY-MM-DD": [contracts...]}."""
    out: dict[str, list[dict]] = {}
    for key, strikes in (exp_date_map or {}).items():
        expiry = key.split(":", 1)[0]  # drop ":DTE" suffix
        contracts = []
        for _strike, listing in strikes.items():
            for c in listing:
                contracts.append(_normalize_contract(c))
        contracts.sort(key=lambda c: float(c["strike"] or 0))
        out[expiry] = contracts
    return out


def _normalize_chain(raw: dict) -> dict:
    """Schwab response → flat OptionChainSnapshot.payload shape."""
    calls_by_exp = _flatten_side(raw.get("callExpDateMap", {}))
    puts_by_exp = _flatten_side(raw.get("putExpDateMap", {}))
    expiries: dict[str, dict] = {}
    for exp in sorted(set(calls_by_exp) | set(puts_by_exp)):
        expiries[exp] = {
            "calls": calls_by_exp.get(exp, []),
            "puts": puts_by_exp.get(exp, []),
        }
    return {
        "underlying_last": _fmt(raw.get("underlyingPrice")),
        "expiries": expiries,
    }
```

- [ ] **Step 4.4: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_normalize.py -v
```
Expected: 2 passed.

- [ ] **Step 4.5: Commit**

```bash
git add backend/apps/market/services/chain.py backend/apps/market/tests/test_chain_normalize.py
git commit -m "feat(market): chain normalizer (Schwab nested → flat per-expiry shape)"
```

---

## Task 5: `fetch_chain` service (cache + persist + Schwab call)

**Files:**
- Modify: `backend/apps/market/services/chain.py`
- Test: `backend/apps/market/tests/test_chain_service.py`

- [ ] **Step 5.1: Write the failing test**

`backend/apps/market/tests/test_chain_service.py`:
```python
from unittest.mock import MagicMock, patch

import pytest
from apps.market.models import OptionChainSnapshot
from apps.market.services.chain import fetch_chain


SCHWAB_RAW = {
    "underlyingPrice": 521.30,
    "callExpDateMap": {"2026-04-25:8": {"515.0": [{"strikePrice": 515.0, "bid": 7.20}]}},
    "putExpDateMap": {},
}


@pytest.mark.django_db
def test_fetch_chain_calls_schwab_and_persists():
    fake_resp = MagicMock()
    fake_resp.json.return_value = SCHWAB_RAW
    fake_client = MagicMock()
    fake_client.get_option_chain.return_value = fake_resp

    with patch("apps.market.services.chain.get_schwab_client", return_value=fake_client), \
         patch("apps.market.services.chain.cache.get_or_fetch") as fake_cache:
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        out = fetch_chain("SPY")

    assert out["underlying_last"] == "521.30"
    assert OptionChainSnapshot.objects.filter(ticker="SPY").count() == 1
    fake_client.get_option_chain.assert_called_once()


@pytest.mark.django_db
def test_fetch_chain_cache_hit_skips_schwab_and_persist():
    cached_payload = {"underlying_last": "100.00", "expiries": {}}
    with patch("apps.market.services.chain.get_schwab_client") as fake_client_factory, \
         patch("apps.market.services.chain.cache.get_or_fetch", return_value=cached_payload):
        out = fetch_chain("SPY")

    assert out == cached_payload
    fake_client_factory.assert_not_called()
    assert OptionChainSnapshot.objects.count() == 0
```

- [ ] **Step 5.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_service.py -v
```
Expected: ERROR — `fetch_chain` not defined.

- [ ] **Step 5.3: Implement `fetch_chain`**

Append to `backend/apps/market/services/chain.py`:
```python
import hashlib
import json

from apps.market import cache
from apps.market.models import OptionChainSnapshot
from apps.market.schwab_client import get_schwab_client


def fetch_chain(
    ticker: str,
    *,
    expiries: int = 4,
    strikes_around_atm: int = 10,
) -> dict:
    """Fetch + cache + persist an option chain for `ticker`.

    Cache key:  market:chain:<TICKER>:<params_hash>  TTL 15s.
    On cache miss: call Schwab, normalize, persist OptionChainSnapshot, return payload.
    On cache hit: return cached payload (no DB write).
    """
    ticker = ticker.upper()
    params_hash = hashlib.sha1(
        json.dumps({"e": expiries, "k": strikes_around_atm}, sort_keys=True).encode(),
    ).hexdigest()[:8]
    cache_key = f"market:chain:{ticker}:{params_hash}"

    def _fetch_and_persist() -> dict:
        client = get_schwab_client()
        resp = client.get_option_chain(
            symbol=ticker,
            contract_type=client.Options.ContractType.ALL,
            strike_count=strikes_around_atm * 2,
            include_underlying_quote=True,
        )
        raw = resp.json()
        payload = _normalize_chain(raw)
        payload["ticker"] = ticker  # stamp for downstream serializer
        OptionChainSnapshot.objects.create(
            ticker=ticker,
            expiries=list(payload["expiries"].keys()),
            payload=payload,
        )
        return payload

    return cache.get_or_fetch(
        cache_key,
        ttl_seconds=cache.ttl_for_kind("chain"),
        fetcher=_fetch_and_persist,
    )
```

- [ ] **Step 5.4: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_service.py -v
```
Expected: 2 passed.

- [ ] **Step 5.5: Commit**

```bash
git add backend/apps/market/services/chain.py backend/apps/market/tests/test_chain_service.py
git commit -m "feat(market): fetch_chain service (Redis 15s cache + per-fetch persistence)"
```

---

## Task 6: `/api/market/chain/` endpoint

**Files:**
- Modify: `backend/apps/market/views.py`
- Modify: `backend/apps/market/urls.py`
- Test: `backend/apps/market/tests/test_chain_endpoint.py`

- [ ] **Step 6.1: Write the failing test**

`backend/apps/market/tests/test_chain_endpoint.py`:
```python
from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_chain_endpoint_returns_payload():
    payload = {"underlying_last": "521.30", "expiries": {"2026-04-25": {"calls": [], "puts": []}}}
    with patch("apps.market.views.fetch_chain", return_value=payload):
        resp = Client().get("/api/market/chain/?ticker=SPY")
    assert resp.status_code == 200
    body = resp.json()
    assert body["underlying_last"] == "521.30"
    assert "2026-04-25" in body["expiries"]


@pytest.mark.django_db
def test_chain_endpoint_missing_ticker_returns_400():
    resp = Client().get("/api/market/chain/")
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_ticker"
```

- [ ] **Step 6.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_endpoint.py -v
```
Expected: 404 / route not found.

- [ ] **Step 6.3: Add view**

Append to `backend/apps/market/views.py`:
```python
from apps.market.services.chain import fetch_chain


@require_GET
@_wrap_schwab
def chain(request: HttpRequest) -> JsonResponse:
    ticker = request.GET.get("ticker", "").strip()
    if not ticker:
        return _err("missing_ticker", "Provide ?ticker=", 400)
    return JsonResponse(fetch_chain(ticker))
```

- [ ] **Step 6.4: Wire route**

Add to `backend/apps/market/urls.py` urlpatterns:
```python
path("chain/", views.chain, name="chain"),
```

- [ ] **Step 6.5: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_chain_endpoint.py -v
```
Expected: 2 passed.

- [ ] **Step 6.6: Commit**

```bash
git add backend/apps/market/views.py backend/apps/market/urls.py backend/apps/market/tests/test_chain_endpoint.py
git commit -m "feat(market): GET /api/market/chain/?ticker= endpoint"
```

---

## Task 7: Chain serializer for AI payload

**Files:**
- Modify: `backend/apps/snapshots/serializer.py`
- Test: `backend/apps/snapshots/tests/test_serializer_chain.py`

- [ ] **Step 7.1: Write the failing test**

`backend/apps/snapshots/tests/test_serializer_chain.py`:
```python
from apps.snapshots.serializer import _render_chain


CHAIN_PAYLOAD = {
    "underlying_last": "521.30",
    "expiries": {
        "2026-04-25": {
            "calls": [
                {"strike": "515.00", "bid": "7.20", "ask": "7.30", "delta": "0.72",
                 "iv": "18.4", "volume": 1234, "oi": 5678, "gamma": "0.04",
                 "theta": "-0.12", "vega": "0.18", "last": "7.25"},
                {"strike": "520.00", "bid": "3.85", "ask": "3.95", "delta": "0.55",
                 "iv": "17.9", "volume": 999, "oi": 1111, "gamma": "0.05",
                 "theta": "-0.13", "vega": "0.20", "last": "3.90"},
            ],
            "puts": [
                {"strike": "515.00", "bid": "0.95", "ask": "1.00", "delta": "-0.28",
                 "iv": "19.1", "volume": 222, "oi": 4444, "gamma": "0.04",
                 "theta": "-0.10", "vega": "0.18", "last": "0.97"},
            ],
        },
    },
}


def test_render_chain_emits_per_expiry_table():
    md = _render_chain(CHAIN_PAYLOAD, ticker="SPY")
    assert "## Option chain — SPY" in md
    assert "underlying $521.30" in md
    assert "### Expiry 2026-04-25" in md
    # Both call and put for strike 515 appear in the same row
    assert "| 515.00 | 7.20 | 7.30 | 0.72 | 18.4 | 0.95 | 1.00 | -0.28 | 19.1 |" in md
    # Strike 520 has only a call → put cells are em-dashes
    assert "| 520.00 | 3.85 | 3.95 | 0.55 | 17.9 | — | — | — | — |" in md


def test_render_chain_handles_empty_payload():
    out = _render_chain({"underlying_last": None, "expiries": {}}, ticker="XXX")
    assert "_(no expiries)_" in out
```

- [ ] **Step 7.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_chain.py -v
```
Expected: ImportError on `_render_chain`.

- [ ] **Step 7.3: Implement `_render_chain`**

Add to `backend/apps/snapshots/serializer.py`:

```python
def _render_chain(payload: dict, *, ticker: str = "?") -> str:
    underlying = payload.get("underlying_last")
    header = f"## Option chain — {ticker} (underlying ${underlying})" if underlying else f"## Option chain — {ticker}"
    expiries = payload.get("expiries") or {}
    if not expiries:
        return f"{header}\n_(no expiries)_"

    # Front-month + next monthly per spec §5.3 — keep first 2 expiries by sorted date.
    keep = list(sorted(expiries.keys()))[:2]

    lines = [header]
    for exp in keep:
        section = expiries[exp]
        calls_by_strike = {c["strike"]: c for c in section.get("calls", [])}
        puts_by_strike = {p["strike"]: p for p in section.get("puts", [])}
        all_strikes = sorted(set(calls_by_strike) | set(puts_by_strike), key=lambda s: float(s))
        lines.append(f"\n### Expiry {exp}")
        lines.append("| strike | call bid | call ask | call Δ | call IV | put bid | put ask | put Δ | put IV |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for strike in all_strikes:
            c = calls_by_strike.get(strike, {})
            p = puts_by_strike.get(strike, {})
            lines.append(
                f"| {strike} | {c.get('bid') or '—'} | {c.get('ask') or '—'} | "
                f"{c.get('delta') or '—'} | {c.get('iv') or '—'} | "
                f"{p.get('bid') or '—'} | {p.get('ask') or '—'} | "
                f"{p.get('delta') or '—'} | {p.get('iv') or '—'} |"
            )
    return "\n".join(lines)
```

Wire it into the dispatcher. Modify `_render_section`:
```python
def _render_section(kind: str, payload) -> str:
    if kind == "quotes":
        return _render_quotes(payload)
    if kind == "ohlc":
        return _render_ohlc(payload)
    if kind == "positions":
        return _render_positions(payload)
    if kind == "breadth":
        return _render_breadth(payload)
    if kind == "news":
        return _render_news(payload)
    if kind == "chain":
        return _render_chain(payload, ticker=payload.get("ticker", "?"))
    if kind == "notes":
        return ""
    return f"## {_title(kind)}\n```json\n{payload}\n```"
```

The chain payload now carries `ticker` (stamped in Task 5), so no additional arg threading is needed at the call site.

- [ ] **Step 7.4: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_chain.py -v
```
Expected: 2 passed.

- [ ] **Step 7.5: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_chain.py
git commit -m "feat(snapshots): chain serializer (per-expiry call/put table, ±10 strikes ATM)"
```

---

## Task 8: `fetch_news` service (Finnhub) + dedup

**Files:**
- Create: `backend/apps/market/services/news.py`
- Test: `backend/apps/market/tests/test_news_service.py`

- [ ] **Step 8.1: Write the failing test**

`backend/apps/market/tests/test_news_service.py`:
```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from apps.market.models import NewsItem
from apps.market.services.news import fetch_news


def _resp(items):
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = items
    r.raise_for_status = lambda: None
    return r


FINNHUB_SPY = [
    {"id": 11, "headline": "SPY climbs on Fed minutes", "summary": "Markets rally...",
     "url": "https://example.com/1", "source": "Reuters",
     "datetime": int(datetime(2026, 4, 17, 9, 12, tzinfo=timezone.utc).timestamp()),
     "related": "SPY"},
    {"id": 12, "headline": "Tech leads gains", "summary": "",
     "url": "https://example.com/2", "source": "Bloomberg",
     "datetime": int(datetime(2026, 4, 17, 8, 45, tzinfo=timezone.utc).timestamp()),
     "related": "SPY"},
]


@pytest.mark.django_db
def test_fetch_news_calls_finnhub_per_ticker_and_dedups():
    with patch("apps.market.services.news._finnhub_get") as fake_get, \
         patch("apps.market.services.news._finnhub_api_key", return_value="k"), \
         patch("apps.market.services.news.cache.get_or_fetch") as fake_cache:
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        fake_get.return_value = FINNHUB_SPY
        items = fetch_news(["SPY"])

    assert len(items) == 2
    assert items[0]["headline"] == "SPY climbs on Fed minutes"  # newest first
    assert NewsItem.objects.count() == 2

    # Re-fetch: dedup keeps row count stable.
    with patch("apps.market.services.news._finnhub_get", return_value=FINNHUB_SPY), \
         patch("apps.market.services.news._finnhub_api_key", return_value="k"), \
         patch("apps.market.services.news.cache.get_or_fetch") as fake_cache:
        fake_cache.side_effect = lambda key, *, ttl_seconds, fetcher: fetcher()
        fetch_news(["SPY"])
    assert NewsItem.objects.count() == 2


@pytest.mark.django_db
def test_fetch_news_no_credential_returns_empty():
    with patch("apps.market.services.news._finnhub_api_key", return_value=None):
        items = fetch_news(["SPY"])
    assert items == []
```

- [ ] **Step 8.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/market/tests/test_news_service.py -v
```
Expected: ERROR — `news.py` doesn't exist.

- [ ] **Step 8.3: Implement `fetch_news`**

`backend/apps/market/services/news.py`:
```python
"""News fetching from Finnhub. One concrete impl, no abstraction (M5 scope)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

from apps.market import cache
from apps.market.models import NewsItem
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="finnhub")
    except ApiCredential.DoesNotExist:
        return None
    token = cred.token or {}
    return token.get("api_key")


def _finnhub_get(path: str, params: dict, api_key: str) -> list[dict]:
    params = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else []


def _upsert_items(provider: str, items: list[dict]) -> list[NewsItem]:
    out: list[NewsItem] = []
    for it in items:
        external_id = str(it.get("id", ""))
        if not external_id:
            continue
        published_at = datetime.fromtimestamp(it.get("datetime", 0), tz=timezone.utc)
        obj, _ = NewsItem.objects.update_or_create(
            provider=provider, external_id=external_id,
            defaults={
                "ticker": (it.get("related") or "").upper(),
                "headline": (it.get("headline") or "")[:512],
                "summary": it.get("summary") or "",
                "url": (it.get("url") or "")[:1024],
                "source": (it.get("source") or "")[:64],
                "published_at": published_at,
            },
        )
        out.append(obj)
    return out


def fetch_news(
    tickers: list[str],
    *,
    lookback_hours: int = 24,
    limit: int = 15,
) -> list[dict]:
    """Fetch + dedup news for `tickers` plus market-wide. Newest-first list capped at `limit`."""
    api_key = _finnhub_api_key()
    if not api_key:
        log.info("Finnhub credential not configured; returning empty news list")
        return []

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(hours=lookback_hours)
    aggregated: list[dict] = []

    for ticker in [t.upper() for t in tickers if t]:
        cache_key = f"market:news:{ticker}:{lookback_hours}"
        items = cache.get_or_fetch(
            cache_key,
            ttl_seconds=cache.ttl_for_kind("news"),
            fetcher=lambda t=ticker: _finnhub_get(
                "/company-news",
                {"symbol": t, "from": str(start), "to": str(end)},
                api_key,
            ),
        )
        _upsert_items("finnhub", items)
        aggregated.extend(items)

    general = cache.get_or_fetch(
        f"market:news:_general_:{lookback_hours}",
        ttl_seconds=cache.ttl_for_kind("news"),
        fetcher=lambda: _finnhub_get("/news", {"category": "general"}, api_key),
    )
    _upsert_items("finnhub", general)
    aggregated.extend(general)

    seen: set[str] = set()
    deduped: list[dict] = []
    for it in aggregated:
        key = str(it.get("id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    deduped.sort(key=lambda it: it.get("datetime", 0), reverse=True)
    return deduped[:limit]
```

- [ ] **Step 8.4: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_news_service.py -v
```
Expected: 2 passed.

- [ ] **Step 8.5: Commit**

```bash
git add backend/apps/market/services/news.py backend/apps/market/tests/test_news_service.py
git commit -m "feat(market): fetch_news service (Finnhub + Redis 5min cache + dedup)"
```

---

## Task 9: `/api/market/news/` endpoint

**Files:**
- Modify: `backend/apps/market/views.py`
- Modify: `backend/apps/market/urls.py`
- Test: `backend/apps/market/tests/test_news_endpoint.py`

- [ ] **Step 9.1: Write the failing test**

`backend/apps/market/tests/test_news_endpoint.py`:
```python
from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_news_endpoint_returns_items():
    items = [
        {"id": 1, "headline": "Hello", "summary": "", "url": "https://x", "source": "R",
         "datetime": 1700000000, "related": "SPY"},
    ]
    with patch("apps.market.views.fetch_news", return_value=items):
        resp = Client().get("/api/market/news/?tickers=SPY,AAPL&lookback=24")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["headline"] == "Hello"


@pytest.mark.django_db
def test_news_endpoint_default_lookback_24():
    with patch("apps.market.views.fetch_news") as fake:
        fake.return_value = []
        Client().get("/api/market/news/?tickers=SPY")
    fake.assert_called_once()
    _, kwargs = fake.call_args
    assert kwargs["lookback_hours"] == 24
```

- [ ] **Step 9.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/market/tests/test_news_endpoint.py -v
```
Expected: 404.

- [ ] **Step 9.3: Add view**

Append to `backend/apps/market/views.py`:
```python
from apps.market.services.news import fetch_news


@require_GET
def news(request: HttpRequest) -> JsonResponse:
    raw_tickers = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw_tickers.split(",") if t.strip()]
    try:
        lookback = int(request.GET.get("lookback", "24"))
    except ValueError:
        return _err("invalid_lookback", "lookback must be int hours", 400)
    items = fetch_news(tickers, lookback_hours=lookback)
    return JsonResponse({"items": items})
```

(Note: no `_wrap_schwab` decorator — news doesn't need Schwab.)

- [ ] **Step 9.4: Wire route**

Add to `backend/apps/market/urls.py` urlpatterns:
```python
path("news/", views.news, name="news"),
```

- [ ] **Step 9.5: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/market/tests/test_news_endpoint.py -v
```
Expected: 2 passed.

- [ ] **Step 9.6: Commit**

```bash
git add backend/apps/market/views.py backend/apps/market/urls.py backend/apps/market/tests/test_news_endpoint.py
git commit -m "feat(market): GET /api/market/news/?tickers=&lookback= endpoint"
```

---

## Task 10: News serializer rewrite (use new richer item shape)

**Files:**
- Modify: `backend/apps/snapshots/serializer.py` (`_render_news`)
- Test: `backend/apps/snapshots/tests/test_serializer_news.py`

The existing `_render_news` operates on a list directly. The new `news` section payload from `_FETCHERS` (Task 14) wraps the list in `{"items": [...]}`. Update both.

- [ ] **Step 10.1: Write the failing test**

`backend/apps/snapshots/tests/test_serializer_news.py`:
```python
from apps.snapshots.serializer import _render_news


PAYLOAD = {
    "items": [
        {"headline": "Fed minutes show split", "source": "Reuters", "summary": "Hawks vs doves",
         "url": "https://x/1", "datetime": 1745484720, "related": "SPY"},
        {"headline": "TSLA Q1 deliveries miss", "source": "Bloomberg", "summary": "",
         "url": "https://x/2", "datetime": 1745482800, "related": "TSLA"},
    ],
}


def test_render_news_emits_dated_list():
    md = _render_news(PAYLOAD)
    assert "## News (last 24h)" in md
    assert "Fed minutes show split" in md
    assert "*Reuters*" in md
    assert "Hawks vs doves" in md
    assert "TSLA Q1 deliveries miss" in md
    assert "*Bloomberg*" in md


def test_render_news_caps_at_15():
    big = {"items": [
        {"headline": f"H{i}", "source": "S", "summary": "", "url": "u",
         "datetime": 1745484720 - i, "related": ""} for i in range(30)
    ]}
    md = _render_news(big)
    assert md.count("- **") == 15


def test_render_news_handles_empty():
    assert "_(no headlines)_" in _render_news({"items": []})
```

- [ ] **Step 10.2: Run test to verify it fails**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_news.py -v
```
Expected: failures — current `_render_news` operates on `list`, new shape is `{"items": [...]}`.

- [ ] **Step 10.3: Update `_render_news`**

Replace the existing `_render_news` in `backend/apps/snapshots/serializer.py`:
```python
from datetime import datetime, timezone


def _render_news(payload) -> str:
    items = payload.get("items", []) if isinstance(payload, dict) else (payload or [])
    if not items:
        return "## News (last 24h)\n_(no headlines)_"
    lines = ["## News (last 24h)", ""]
    for it in items[:15]:
        ts_raw = it.get("datetime") or it.get("published_at")
        if isinstance(ts_raw, int | float):
            when = datetime.fromtimestamp(ts_raw, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        else:
            when = str(ts_raw or "?")
        head = it.get("headline") or "?"
        src = it.get("source") or "?"
        lines.append(f"- **{when}** — *{src}* — {head}")
        summary = (it.get("summary") or "").strip()
        if summary:
            lines.append(f"  {summary}")
    return "\n".join(lines)
```

- [ ] **Step 10.4: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_news.py -v
```
Expected: 3 passed.

- [ ] **Step 10.5: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_news.py
git commit -m "feat(snapshots): news serializer (dated list, cap 15, accepts {items: [...]} shape)"
```

---

## Task 11: Image upload + serve + screenshot service

**Files:**
- Create: `backend/apps/snapshots/services/screenshot.py` (also: convert services.py to package — see Task 13)
- Modify: `backend/apps/snapshots/views.py`
- Modify: `backend/apps/snapshots/urls.py`
- Modify: `backend/apps/snapshots/serializers.py` (add SnapshotImageSerializer)
- Test: `backend/apps/snapshots/tests/test_image_endpoint.py`

This task does the upload, list, and serve endpoints together — they're a tight unit.

- [ ] **Step 11.1: Write the failing test**

`backend/apps/snapshots/tests/test_image_endpoint.py`:
```python
import pytest
from django.test import Client
from apps.snapshots.models import SnapshotImage


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
NOT_PNG = b"GIF89a" + b"\x00" * 50


@pytest.mark.django_db
def test_upload_staged_image_persists_with_null_snapshot():
    resp = Client().post(
        "/api/snapshots/images/?staged=true",
        data=PNG_BYTES, content_type="image/png",
        HTTP_X_CAPTION="SPY 5m",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    img = SnapshotImage.objects.get(id=body["id"])
    assert img.snapshot is None
    assert img.kind == "client_capture"
    assert img.caption == "SPY 5m"
    assert bytes(img.data).startswith(b"\x89PNG")


@pytest.mark.django_db
def test_upload_invalid_png_returns_400():
    resp = Client().post(
        "/api/snapshots/images/?staged=true",
        data=NOT_PNG, content_type="image/png",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_png"


@pytest.mark.django_db
def test_list_staged_returns_only_unattached():
    SnapshotImage.objects.create(snapshot=None, kind="client_capture", data=PNG_BYTES)
    resp = Client().get("/api/snapshots/images/?staged=true")
    assert resp.status_code == 200
    assert len(resp.json()["images"]) == 1


@pytest.mark.django_db
def test_serve_image_returns_bytes():
    img = SnapshotImage.objects.create(snapshot=None, kind="client_capture", data=PNG_BYTES)
    resp = Client().get(f"/api/snapshots/images/{img.id}/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")
```

- [ ] **Step 11.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_image_endpoint.py -v
```
Expected: 404 / endpoint missing.

- [ ] **Step 11.3: Implement screenshot service**

(Note: `services.py` → `services/` package conversion happens in Task 13. For this task, add the new module under `backend/apps/snapshots/services_image.py` to avoid the rename conflict, then Task 13 moves it into the package.)

`backend/apps/snapshots/services_image.py`:
```python
"""Client-side screenshot upload + validation."""
from __future__ import annotations

from apps.snapshots.models import SnapshotImage

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 5 * 1024 * 1024


class InvalidPNGError(ValueError):
    pass


class ImageTooLargeError(ValueError):
    pass


def attach_client_image(
    snapshot_id: int | None, png_bytes: bytes, caption: str = "",
) -> SnapshotImage:
    if not png_bytes.startswith(PNG_MAGIC):
        raise InvalidPNGError("data does not start with PNG magic bytes")
    if len(png_bytes) > MAX_BYTES:
        raise ImageTooLargeError(f"image exceeds {MAX_BYTES} bytes")
    return SnapshotImage.objects.create(
        snapshot_id=snapshot_id, kind="client_capture",
        data=png_bytes, caption=caption[:256],
    )
```

- [ ] **Step 11.4: Add views + serializers**

Add to `backend/apps/snapshots/serializers.py`:
```python
from .models import SnapshotImage


class SnapshotImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnapshotImage
        fields: ClassVar = ["id", "kind", "caption", "created_at", "snapshot_id"]
        read_only_fields: ClassVar = ["created_at"]
```

Append to `backend/apps/snapshots/views.py`:
```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.snapshots.models import SnapshotImage
from apps.snapshots.serializers import SnapshotImageSerializer
from apps.snapshots.services_image import (
    InvalidPNGError, ImageTooLargeError, attach_client_image,
)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def images_collection(request):
    if request.method == "POST":
        body = request.body
        caption = request.headers.get("X-Caption", "")
        try:
            img = attach_client_image(snapshot_id=None, png_bytes=body, caption=caption)
        except InvalidPNGError as e:
            return Response({"code": "invalid_png", "message": str(e)}, status=400)
        except ImageTooLargeError as e:
            return Response({"code": "too_large", "message": str(e)}, status=413)
        return Response(SnapshotImageSerializer(img).data, status=201)

    # GET: list staged
    staged = request.GET.get("staged") == "true"
    qs = SnapshotImage.objects.filter(snapshot__isnull=True) if staged else SnapshotImage.objects.all()
    qs = qs.order_by("-created_at")[:50]
    return Response({"images": SnapshotImageSerializer(qs, many=True).data})


def serve_image(_request, image_id: int):
    try:
        img = SnapshotImage.objects.get(id=image_id)
    except SnapshotImage.DoesNotExist:
        return HttpResponse(status=404)
    return HttpResponse(bytes(img.data), content_type=img.mime_type or "image/png")
```

- [ ] **Step 11.5: Wire routes**

Replace `backend/apps/snapshots/urls.py`:
```python
from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("snapshots", views.SnapshotViewSet, basename="snapshot")

urlpatterns = [
    *router.urls,
    path("snapshots/images/", views.images_collection, name="snapshot-images"),
    path("snapshots/images/<int:image_id>/", views.serve_image, name="snapshot-image-serve"),
]
```

- [ ] **Step 11.6: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_image_endpoint.py -v
```
Expected: 4 passed.

- [ ] **Step 11.7: Commit**

```bash
git add backend/apps/snapshots/services_image.py backend/apps/snapshots/views.py \
        backend/apps/snapshots/urls.py backend/apps/snapshots/serializers.py \
        backend/apps/snapshots/tests/test_image_endpoint.py
git commit -m "feat(snapshots): image upload + list staged + serve endpoints"
```

---

## Task 12: Image serializer for AI provider blocks

**Files:**
- Modify: `backend/apps/snapshots/serializer.py`
- Test: `backend/apps/snapshots/tests/test_serializer_image.py`

- [ ] **Step 12.1: Write the failing test**

`backend/apps/snapshots/tests/test_serializer_image.py`:
```python
import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.serializer import build_image_blocks, _render_image


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


@pytest.fixture
@pytest.mark.django_db
def two_images(db):
    profile = TradingProfile.objects.create(name="P", style_text="x")
    snap = Snapshot.objects.create(profile=profile, includes=["image"])
    a = SnapshotImage.objects.create(snapshot=snap, kind="server_render", data=PNG, caption="SPY 5m, 60 bars")
    b = SnapshotImage.objects.create(snapshot=snap, kind="client_capture", data=PNG, caption="TSLA 1h")
    return [a.id, b.id]


def test_build_image_blocks_claude(two_images):
    blocks = build_image_blocks(two_images, provider_name="claude")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["type"] == "base64"
    assert blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[0]["source"]["data"]


def test_build_image_blocks_openai(two_images):
    blocks = build_image_blocks(two_images, provider_name="openai")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "image_url"
    assert blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_render_image_lists_captions(two_images):
    md = _render_image({"image_ids": two_images})
    assert "## Charts attached" in md
    assert "SPY 5m, 60 bars (server-rendered)" in md
    assert "TSLA 1h (your screenshot)" in md
```

- [ ] **Step 12.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_image.py -v
```
Expected: ImportError on `build_image_blocks`, `_render_image`.

- [ ] **Step 12.3: Implement**

Append to `backend/apps/snapshots/serializer.py`:
```python
import base64

from apps.snapshots.models import SnapshotImage


def build_image_blocks(image_ids: list[int], *, provider_name: str) -> list[dict]:
    """Return provider-shaped image blocks for inline base64 attachment."""
    blocks: list[dict] = []
    for img in SnapshotImage.objects.filter(id__in=image_ids).order_by("id"):
        b64 = base64.b64encode(bytes(img.data)).decode("ascii")
        if provider_name == "claude":
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": img.mime_type or "image/png", "data": b64},
            })
        else:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img.mime_type or 'image/png'};base64,{b64}"},
            })
    return blocks


def _render_image(payload: dict) -> str:
    ids = payload.get("image_ids") or []
    if not ids:
        return "## Charts attached\n_(none)_"
    rows = ["## Charts attached"]
    for img in SnapshotImage.objects.filter(id__in=ids).order_by("id"):
        suffix = "server-rendered" if img.kind == "server_render" else "your screenshot"
        cap = img.caption or "(no caption)"
        rows.append(f"- chart_{img.id}: {cap} ({suffix})")
    return "\n".join(rows)
```

Wire `_render_image` into `_render_section`:
```python
    if kind == "image":
        return _render_image(payload)
```

- [ ] **Step 12.4: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_serializer_image.py -v
```
Expected: 3 passed.

- [ ] **Step 12.5: Commit**

```bash
git add backend/apps/snapshots/serializer.py backend/apps/snapshots/tests/test_serializer_image.py
git commit -m "feat(snapshots): image serializer + provider-shaped image blocks (Claude / OpenAI)"
```

---

## Task 13: Reorganize `services.py` → `services/` package

**Files:**
- Move: `backend/apps/snapshots/services.py` → `backend/apps/snapshots/services/__init__.py` (preserve existing API)
- Move: `backend/apps/snapshots/services_image.py` → `backend/apps/snapshots/services/screenshot.py`
- Update imports: `backend/apps/snapshots/views.py`, `backend/apps/snapshots/tasks.py`

- [ ] **Step 13.1: Move services.py into a package**

```bash
mkdir -p backend/apps/snapshots/services
git mv backend/apps/snapshots/services.py backend/apps/snapshots/services/__init__.py
git mv backend/apps/snapshots/services_image.py backend/apps/snapshots/services/screenshot.py
```

- [ ] **Step 13.2: Update import in `views.py`**

In `backend/apps/snapshots/views.py`, change:
```python
from apps.snapshots.services_image import (
    InvalidPNGError, ImageTooLargeError, attach_client_image,
)
```
to:
```python
from apps.snapshots.services.screenshot import (
    InvalidPNGError, ImageTooLargeError, attach_client_image,
)
```

`tasks.py`'s `from apps.snapshots.services import capture_for_existing` keeps working because `__init__.py` re-exports it.

- [ ] **Step 13.3: Run the relevant tests**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/ -v
```
Expected: all green.

- [ ] **Step 13.4: Commit**

```bash
git add -A backend/apps/snapshots/services backend/apps/snapshots/views.py
git commit -m "refactor(snapshots): convert services.py to services/ package"
```

---

## Task 14: Wire `chain` / `news` / `image` into `_FETCHERS`

**Files:**
- Modify: `backend/apps/snapshots/services/__init__.py` (add fetchers, pass `snapshot_id` through)
- Modify: `backend/apps/market/services/chain.py` (stamp ticker into payload for serializer)
- Modify: `backend/apps/snapshots/serializer.py` (now `payload["ticker"]` works for chain — drop the helper hack)
- Test: `backend/apps/snapshots/tests/test_capture_extended.py`

- [ ] **Step 14.1: Write the failing test**

`backend/apps/snapshots/tests/test_capture_extended.py`:
```python
from unittest.mock import patch

import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import SnapshotImage
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_capture_with_chain_news_image_sections():
    profile = TradingProfile.objects.create(name="P", style_text="x")

    fake_chain = {"ticker": "SPY", "underlying_last": "521.30", "expiries": {}}
    fake_news_items = [{"id": 1, "headline": "h", "summary": "", "url": "u",
                        "source": "S", "datetime": 1700000000, "related": "SPY"}]

    def fake_render(ticker, timeframe, bars, *, snapshot_id):
        img = SnapshotImage.objects.create(
            snapshot_id=snapshot_id, kind="server_render",
            data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
            caption=f"{ticker} {timeframe}, {bars} bars",
        )
        return img

    with patch("apps.market.services.chain.fetch_chain", return_value=fake_chain), \
         patch("apps.market.services.news.fetch_news", return_value=fake_news_items), \
         patch("apps.snapshots.services.render.render_chart_png", side_effect=fake_render):
        snap = capture(
            profile=profile, objective="o", includes=["chain", "news", "image"],
            watchlist_tickers=["SPY"],
            ohlc_ticker="SPY", ohlc_timeframe="5m", ohlc_bars=60,
        )

    assert snap.status == "ready"
    sec_kinds = {s.kind: s for s in snap.sections.all()}
    assert sec_kinds["chain"].status == "done"
    assert sec_kinds["chain"].payload["ticker"] == "SPY"
    assert sec_kinds["news"].status == "done"
    assert sec_kinds["news"].payload["items"][0]["headline"] == "h"
    assert sec_kinds["image"].status == "done"
    assert len(sec_kinds["image"].payload["image_ids"]) == 1
    assert SnapshotImage.objects.filter(snapshot=snap).count() == 1
```

- [ ] **Step 14.2: Run test to verify failure**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_capture_extended.py -v
```
Expected: failure — `_FETCHERS` doesn't have chain/news/image entries; `apps.snapshots.services.render` doesn't exist yet.

- [ ] **Step 14.3: Add render placeholder module**

(The real implementation lands in Task 26; for now stub it so `_FETCHERS` can import.)

`backend/apps/snapshots/services/render.py`:
```python
"""Server-side chart rendering via Playwright. Real impl in Task 26."""
from __future__ import annotations

from apps.snapshots.models import SnapshotImage


def render_chart_png(ticker: str, timeframe: str, bars: int, *, snapshot_id: int) -> SnapshotImage:
    raise NotImplementedError("Playwright render arrives in Task 26")
```

- [ ] **Step 14.4: Wire fetchers**

Update `backend/apps/snapshots/services/__init__.py`. Add imports near the top:
```python
from apps.market.services.chain import fetch_chain
from apps.market.services.news import fetch_news
from apps.snapshots.services.render import render_chart_png
```

Extend the `_FETCHERS` dict (replace existing dict literal):
```python
_FETCHERS = {
    "quotes": lambda *, watchlist_tickers, **_: {"data": fetch_quotes(watchlist_tickers)},
    "ohlc": lambda *, watchlist_tickers, ohlc_ticker=None, ohlc_timeframe="1m", ohlc_bars=60, **_: {
        "data": {
            "ticker": ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
            "timeframe": ohlc_timeframe,
            "bars": fetch_ohlc(
                ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
                timeframe=ohlc_timeframe, bars=ohlc_bars,
            ),
        },
    },
    "positions": lambda **_: {"data": fetch_positions()},
    "breadth": lambda **_: {"data": fetch_market_context()},
    "notes": lambda **_: {"data": {}},
    "chain": lambda *, watchlist_tickers, **_: {
        "data": fetch_chain(watchlist_tickers[0] if watchlist_tickers else "SPY"),
    },
    "news": lambda *, watchlist_tickers, **_: {
        "data": {"items": fetch_news(list(watchlist_tickers))},
    },
    "image": lambda *, snapshot_id, watchlist_tickers, ohlc_ticker, ohlc_timeframe, ohlc_bars, **_: {
        "data": {"image_ids": [
            render_chart_png(
                ohlc_ticker or (watchlist_tickers[0] if watchlist_tickers else "SPY"),
                ohlc_timeframe, ohlc_bars, snapshot_id=snapshot_id,
            ).id,
        ]},
    },
}
```

Pass `snapshot_id` from `capture_for_existing` into the fetcher call:
```python
            result = fetcher(
                snapshot_id=snap.id,
                watchlist_tickers=list(watchlist_tickers),
                ohlc_ticker=ohlc_ticker,
                ohlc_timeframe=ohlc_timeframe,
                ohlc_bars=ohlc_bars,
            )
```

- [ ] **Step 14.5: Run test, expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_capture_extended.py -v
```
Expected: 1 passed.

- [ ] **Step 14.6: Commit**

```bash
git add backend/apps/snapshots/services/__init__.py backend/apps/snapshots/services/render.py \
        backend/apps/snapshots/tests/test_capture_extended.py
git commit -m "feat(snapshots): wire chain/news/image into _FETCHERS, pass snapshot_id"
```

---

## Task 15: Token-budget keeps images, prunes chain/news/ohlc

**Files:**
- Modify: `backend/apps/snapshots/token_budget.py`
- Test: `backend/apps/snapshots/tests/test_token_budget_image.py`

The existing `_PRUNE_ORDER` is already `["chain", "news", "ohlc", "breadth", "quotes", "positions"]` — image is absent, so it's already never pruned. Add an explicit test guarding that.

- [ ] **Step 15.1: Write the failing test**

`backend/apps/snapshots/tests/test_token_budget_image.py`:
```python
from apps.snapshots.token_budget import prune_to_budget


def test_image_section_never_pruned_even_under_tight_budget():
    sections = {
        "image": "## Charts attached\n- chart_1: x",
        "chain": "## Option chain\n" + ("X" * 5000),
        "news": "## News\n" + ("Y" * 5000),
        "ohlc": "## OHLC\n" + ("Z" * 5000),
    }
    kept, pruned = prune_to_budget(sections, max_tokens=50)
    assert "image" in kept
    assert "chain" in pruned
```

- [ ] **Step 15.2: Run test, expect green (existing behavior already correct)**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_token_budget_image.py -v
```
Expected: 1 passed (no code change required — test guards against future regressions).

- [ ] **Step 15.3: Commit**

```bash
git add backend/apps/snapshots/tests/test_token_budget_image.py
git commit -m "test(snapshots): guard image section against token-budget pruning"
```

---

## Task 16: Frontend deps — `lightweight-charts` + `html2canvas`

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json` (auto-generated)

- [ ] **Step 16.1: Add deps**

```bash
docker compose exec frontend npm install lightweight-charts@^4.2.0 html2canvas@^1.4.1
```
Expected: package.json + package-lock.json updated; deps install without error.

- [ ] **Step 16.2: Smoke import**

```bash
docker compose exec frontend node -e "console.log(Object.keys(require('lightweight-charts')).slice(0, 5))"
docker compose exec frontend node -e "console.log(typeof require('html2canvas'))"
```
Expected: prints a list of exports + `'function'`.

- [ ] **Step 16.3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add lightweight-charts + html2canvas for M5"
```

---

## Task 17: `Chart.tsx` component

**Files:**
- Create: `frontend/src/components/Chart.tsx`
- Test: `frontend/src/__tests__/Chart.test.tsx`

- [ ] **Step 17.1: Write the failing test**

`frontend/src/__tests__/Chart.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Chart from "../components/Chart";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [
        { ts: "2026-04-17T09:30:00Z", open: 520, high: 522, low: 519, close: 521, volume: 1000 },
      ]}),
    }),
  ) as never;
});

describe("Chart", () => {
  it("renders without crashing and calls onReady once data loads", async () => {
    const onReady = vi.fn();
    render(<Chart ticker="SPY" timeframe="5m" bars={60} onReady={onReady} />, { wrapper });
    await waitFor(() => expect(onReady).toHaveBeenCalled());
  });
});
```

- [ ] **Step 17.2: Run test to verify failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/Chart.test.tsx
```
Expected: ERROR — `Chart` not found.

- [ ] **Step 17.3: Implement `Chart.tsx`**

`frontend/src/components/Chart.tsx`:
```typescript
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { createChart, IChartApi, ISeriesApi } from "lightweight-charts";

export interface ChartProps {
  ticker: string;
  timeframe: string;
  bars: number;
  onReady?: () => void;
}

interface OHLCBar {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface OHLCResponse {
  ticker: string;
  timeframe: string;
  bars: OHLCBar[];
}

export default function Chart({ ticker, timeframe, bars, onReady }: ChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const { data } = useQuery<OHLCResponse>({
    queryKey: ["ohlc", ticker, timeframe, bars],
    queryFn: async () => {
      const r = await fetch(
        `/api/market/ohlc/?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&bars=${bars}`,
      );
      if (!r.ok) throw new Error(`OHLC ${r.status}`);
      return r.json();
    },
  });

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;
    chartRef.current = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: "#0a0a0a" }, textColor: "#d0d0d0" },
      grid: { vertLines: { color: "#1a1a1a" }, horzLines: { color: "#1a1a1a" } },
    });
    seriesRef.current = chartRef.current.addCandlestickSeries();
    return () => {
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!data?.bars?.length || !seriesRef.current) return;
    seriesRef.current.setData(
      data.bars.map((b) => ({
        time: Math.floor(new Date(b.ts).getTime() / 1000) as never,
        open: b.open, high: b.high, low: b.low, close: b.close,
      })),
    );
    chartRef.current?.timeScale().fitContent();
    onReady?.();
  }, [data, onReady]);

  return <div id="chart-root" ref={containerRef} style={{ width: "100%", height: "100%", minHeight: 360 }} />;
}
```

- [ ] **Step 17.4: Run test, expect green**

```bash
docker compose exec frontend npx vitest run src/__tests__/Chart.test.tsx
```
Expected: 1 passed.

- [ ] **Step 17.5: Commit**

```bash
git add frontend/src/components/Chart.tsx frontend/src/__tests__/Chart.test.tsx
git commit -m "feat(frontend): Chart.tsx (lightweight-charts wrapper, fires onReady)"
```

---

## Task 18: `ChartCaptureButton.tsx`

**Files:**
- Create: `frontend/src/components/ChartCaptureButton.tsx`
- Test: `frontend/src/__tests__/ChartCaptureButton.test.tsx`

- [ ] **Step 18.1: Write the failing test**

`frontend/src/__tests__/ChartCaptureButton.test.tsx`:
```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ChartCaptureButton from "../components/ChartCaptureButton";

const fakeBlob = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: "image/png" });

vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({
    toBlob: (cb: (b: Blob) => void) => cb(fakeBlob),
  })),
}));

beforeEach(() => {
  localStorage.clear();
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 42 }) }),
  ) as never;
});

describe("ChartCaptureButton", () => {
  it("captures chart, posts PNG, stores image ID in localStorage", async () => {
    const ref = { current: document.createElement("div") };
    render(<ChartCaptureButton targetRef={ref} caption="SPY 5m" />);
    fireEvent.click(screen.getByRole("button", { name: /capture/i }));
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("staged_image_ids") || "[]");
      expect(stored).toEqual([42]);
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/snapshots/images/?staged=true",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
```

- [ ] **Step 18.2: Run test to verify failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/ChartCaptureButton.test.tsx
```
Expected: ERROR — component missing.

- [ ] **Step 18.3: Implement**

`frontend/src/components/ChartCaptureButton.tsx`:
```typescript
import { useState } from "react";
import html2canvas from "html2canvas";

export interface ChartCaptureButtonProps {
  targetRef: React.RefObject<HTMLElement>;
  caption?: string;
}

const STORAGE_KEY = "staged_image_ids";

function appendStaged(id: number) {
  const cur = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]") as number[];
  cur.push(id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cur));
}

export default function ChartCaptureButton({ targetRef, caption = "" }: ChartCaptureButtonProps) {
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  async function capture() {
    if (!targetRef.current) return;
    setBusy(true);
    try {
      const canvas = await html2canvas(targetRef.current);
      const blob: Blob = await new Promise((resolve, reject) =>
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("no blob"))), "image/png"),
      );
      const resp = await fetch("/api/snapshots/images/?staged=true", {
        method: "POST",
        headers: { "Content-Type": "image/png", "X-Caption": caption },
        body: blob,
      });
      if (!resp.ok) throw new Error(`upload failed ${resp.status}`);
      const body: { id: number } = await resp.json();
      appendStaged(body.id);
      setToast("Captured — will attach to your next snapshot.");
      setTimeout(() => setToast(""), 2500);
    } catch (e) {
      setToast(`Capture failed: ${(e as Error).message}`);
      setTimeout(() => setToast(""), 4000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ position: "absolute", top: 8, right: 8, zIndex: 10 }}>
      <button
        type="button"
        onClick={capture}
        disabled={busy}
        style={{
          background: "rgba(20,20,20,0.7)",
          color: "#fff",
          border: "1px solid #333",
          padding: "4px 10px",
          borderRadius: 4,
          cursor: busy ? "wait" : "pointer",
        }}
      >
        {busy ? "Capturing…" : "Capture chart"}
      </button>
      {toast && (
        <div
          role="status"
          style={{ marginTop: 6, background: "rgba(20,20,20,0.85)", color: "#fff",
                   padding: "4px 8px", borderRadius: 4, fontSize: 12 }}
        >{toast}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 18.4: Run test, expect green**

```bash
docker compose exec frontend npx vitest run src/__tests__/ChartCaptureButton.test.tsx
```
Expected: 1 passed.

- [ ] **Step 18.5: Commit**

```bash
git add frontend/src/components/ChartCaptureButton.tsx frontend/src/__tests__/ChartCaptureButton.test.tsx
git commit -m "feat(frontend): ChartCaptureButton (html2canvas → /api/snapshots/images?staged=true)"
```

---

## Task 19: `RenderChart.tsx` + `/render/chart` route

**Files:**
- Create: `frontend/src/pages/RenderChart.tsx`
- Modify: `frontend/src/App.tsx` (add route)
- Test: `frontend/src/__tests__/RenderChart.test.tsx`

- [ ] **Step 19.1: Write the failing test**

`frontend/src/__tests__/RenderChart.test.tsx`:
```typescript
import { describe, it, expect, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import RenderChart from "../pages/RenderChart";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

global.fetch = vi.fn(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [{ ts: "2026-04-17T09:30:00Z", open: 1, high: 2, low: 1, close: 2, volume: 0 }] }) }),
) as never;

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("RenderChart", () => {
  it("sets data-render-ready on body once chart finishes painting", async () => {
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/render/chart?ticker=SPY&timeframe=5m&bars=10"]}>
          <Routes><Route path="/render/chart" element={<RenderChart />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(document.body.dataset.renderReady).toBe("true"));
  });
});
```

- [ ] **Step 19.2: Run test to verify failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/RenderChart.test.tsx
```
Expected: ERROR — `RenderChart` not found.

- [ ] **Step 19.3: Implement `RenderChart`**

`frontend/src/pages/RenderChart.tsx`:
```typescript
import { useSearchParams } from "react-router-dom";
import Chart from "../components/Chart";

export default function RenderChart() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker") ?? "SPY";
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "60");

  function onReady() {
    document.body.dataset.renderReady = "true";
  }

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0a0a0a" }}>
      <Chart ticker={ticker} timeframe={timeframe} bars={bars} onReady={onReady} />
    </div>
  );
}
```

- [ ] **Step 19.4: Wire route in `App.tsx`**

In `frontend/src/App.tsx`, find the `<Routes>` block and add (alongside other `<Route>` entries):
```typescript
import RenderChart from "./pages/RenderChart";
// ... inside <Routes>:
<Route path="/render/chart" element={<RenderChart />} />
```

(For prod hash-mode parity, also accept it via the same path — React Router will match on either history-mode `/render/chart` or hash-mode `#/render/chart`. No further code needed in M5.)

- [ ] **Step 19.5: Run test, expect green**

```bash
docker compose exec frontend npx vitest run src/__tests__/RenderChart.test.tsx
```
Expected: 1 passed.

- [ ] **Step 19.6: Commit**

```bash
git add frontend/src/pages/RenderChart.tsx frontend/src/App.tsx frontend/src/__tests__/RenderChart.test.tsx
git commit -m "feat(frontend): RenderChart page + /render/chart route (data-render-ready signal)"
```

---

## Task 20: `OptionChainTable.tsx`

**Files:**
- Create: `frontend/src/components/OptionChainTable.tsx`
- Test: `frontend/src/__tests__/OptionChainTable.test.tsx`

- [ ] **Step 20.1: Write the failing test**

`frontend/src/__tests__/OptionChainTable.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import OptionChainTable from "../components/OptionChainTable";

const PAYLOAD = {
  underlying_last: "521.30",
  expiries: {
    "2026-04-25": {
      calls: [
        { strike: "515.00", bid: "7.20", ask: "7.30", delta: "0.72", iv: "18.4" },
        { strike: "520.00", bid: "3.85", ask: "3.95", delta: "0.55", iv: "17.9" },
      ],
      puts: [
        { strike: "515.00", bid: "0.95", ask: "1.00", delta: "-0.28", iv: "19.1" },
      ],
    },
  },
};

describe("OptionChainTable", () => {
  it("renders rows for both calls and puts at the same strike", () => {
    render(<OptionChainTable payload={PAYLOAD} />);
    expect(screen.getByText("521.30")).toBeInTheDocument();
    expect(screen.getByText("515.00")).toBeInTheDocument();
    expect(screen.getByText("7.20")).toBeInTheDocument();
    expect(screen.getByText("0.95")).toBeInTheDocument();
  });
});
```

- [ ] **Step 20.2: Run test to verify failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/OptionChainTable.test.tsx
```
Expected: ERROR — component missing.

- [ ] **Step 20.3: Implement**

`frontend/src/components/OptionChainTable.tsx`:
```typescript
import { useState } from "react";

interface Contract {
  strike: string;
  bid?: string | null;
  ask?: string | null;
  delta?: string | null;
  iv?: string | null;
  volume?: number;
  oi?: number;
}

interface ChainPayload {
  ticker?: string;
  underlying_last: string | null;
  expiries: Record<string, { calls: Contract[]; puts: Contract[] }>;
}

export default function OptionChainTable({ payload }: { payload: ChainPayload | null }) {
  const expiryDates = payload ? Object.keys(payload.expiries).sort() : [];
  const [selected, setSelected] = useState(expiryDates[0] || "");

  if (!payload || expiryDates.length === 0) {
    return <div style={{ padding: 12, color: "#888" }}>No chain data.</div>;
  }
  const exp = payload.expiries[selected] || payload.expiries[expiryDates[0]];
  const callsByStrike = new Map(exp.calls.map((c) => [c.strike, c]));
  const putsByStrike = new Map(exp.puts.map((p) => [p.strike, p]));
  const strikes = [...new Set([...callsByStrike.keys(), ...putsByStrike.keys()])]
    .sort((a, b) => parseFloat(a) - parseFloat(b));
  const atm = payload.underlying_last ? parseFloat(payload.underlying_last) : null;

  return (
    <div style={{ padding: 8 }}>
      <div style={{ marginBottom: 8 }}>
        <strong>Underlying:</strong> {payload.underlying_last}
      </div>
      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        {expiryDates.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setSelected(d)}
            style={{
              background: d === selected ? "#2a2a2a" : "#111",
              color: "#fff",
              border: "1px solid #333",
              padding: "4px 8px",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >{d}</button>
        ))}
      </div>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #333" }}>
            <th style={{ textAlign: "right" }}>call bid</th>
            <th style={{ textAlign: "right" }}>call ask</th>
            <th style={{ textAlign: "right" }}>call Δ</th>
            <th style={{ textAlign: "right" }}>call IV</th>
            <th style={{ textAlign: "center" }}>strike</th>
            <th style={{ textAlign: "right" }}>put bid</th>
            <th style={{ textAlign: "right" }}>put ask</th>
            <th style={{ textAlign: "right" }}>put Δ</th>
            <th style={{ textAlign: "right" }}>put IV</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((strike) => {
            const c = callsByStrike.get(strike) || {} as Contract;
            const p = putsByStrike.get(strike) || {} as Contract;
            const isAtm = atm !== null && Math.abs(parseFloat(strike) - atm) < 0.5;
            return (
              <tr key={strike} style={{ background: isAtm ? "#1a2a3a" : "transparent" }}>
                <td style={{ textAlign: "right" }}>{c.bid ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{c.ask ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{c.delta ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{c.iv ?? "—"}</td>
                <td style={{ textAlign: "center", fontWeight: isAtm ? "bold" : "normal" }}>{strike}</td>
                <td style={{ textAlign: "right" }}>{p.bid ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{p.ask ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{p.delta ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{p.iv ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 20.4: Run test, expect green**

```bash
docker compose exec frontend npx vitest run src/__tests__/OptionChainTable.test.tsx
```
Expected: 1 passed.

- [ ] **Step 20.5: Commit**

```bash
git add frontend/src/components/OptionChainTable.tsx frontend/src/__tests__/OptionChainTable.test.tsx
git commit -m "feat(frontend): OptionChainTable (expiry tabs + per-strike call/put row, ATM highlight)"
```

---

## Task 21: `NewsFeed.tsx`

**Files:**
- Create: `frontend/src/components/NewsFeed.tsx`
- Test: `frontend/src/__tests__/NewsFeed.test.tsx`

- [ ] **Step 21.1: Write the failing test**

`frontend/src/__tests__/NewsFeed.test.tsx`:
```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import NewsFeed from "../components/NewsFeed";

const ITEMS = [
  { id: 1, headline: "Older", source: "R", summary: "", url: "https://x/1", datetime: 1000 },
  { id: 2, headline: "Newer", source: "B", summary: "Sub", url: "https://x/2", datetime: 2000 },
];

describe("NewsFeed", () => {
  it("renders newest first and links headlines", () => {
    render(<NewsFeed items={ITEMS} />);
    const headlines = screen.getAllByRole("link").map((a) => a.textContent);
    expect(headlines[0]).toBe("Newer");
    expect(headlines[1]).toBe("Older");
  });

  it("shows empty state with no items", () => {
    render(<NewsFeed items={[]} />);
    expect(screen.getByText(/no headlines/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 21.2: Run test to verify failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/NewsFeed.test.tsx
```
Expected: ERROR — component missing.

- [ ] **Step 21.3: Implement**

`frontend/src/components/NewsFeed.tsx`:
```typescript
interface NewsItem {
  id: number | string;
  headline: string;
  summary?: string;
  source?: string;
  url: string;
  datetime: number;
}

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function NewsFeed({ items }: { items: NewsItem[] }) {
  if (!items.length) {
    return <div style={{ padding: 12, color: "#888" }}>No headlines.</div>;
  }
  const sorted = [...items].sort((a, b) => b.datetime - a.datetime).slice(0, 15);
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {sorted.map((it) => (
        <li key={it.id} style={{ padding: "8px 12px", borderBottom: "1px solid #222" }}>
          <div style={{ fontSize: 11, color: "#999" }}>
            {fmt(it.datetime)} — {it.source ?? "?"}
          </div>
          <a
            href={it.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#9ecbff", fontSize: 14 }}
          >{it.headline}</a>
          {it.summary && <div style={{ fontSize: 12, color: "#bbb", marginTop: 2 }}>{it.summary}</div>}
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 21.4: Run test, expect green**

```bash
docker compose exec frontend npx vitest run src/__tests__/NewsFeed.test.tsx
```
Expected: 2 passed.

- [ ] **Step 21.5: Commit**

```bash
git add frontend/src/components/NewsFeed.tsx frontend/src/__tests__/NewsFeed.test.tsx
git commit -m "feat(frontend): NewsFeed (sorted newest-first, capped 15, links open new tab)"
```

---

## Task 22: `MarketTickerPage.tsx` + `/market/:ticker` route

**Files:**
- Create: `frontend/src/pages/MarketTickerPage.tsx`
- Modify: `frontend/src/App.tsx` (route)
- Test: `frontend/src/__tests__/MarketTickerPage.test.tsx`

- [ ] **Step 22.1: Write the failing test**

`frontend/src/__tests__/MarketTickerPage.test.tsx`:
```typescript
import { describe, it, expect, vi } from "vitest";
import { render, waitFor, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MarketTickerPage from "../pages/MarketTickerPage";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

global.fetch = vi.fn((url: string) => {
  if (url.includes("/api/market/chain/")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({
      underlying_last: "100.00", expiries: { "2026-04-25": { calls: [], puts: [] } },
    })});
  }
  if (url.includes("/api/market/news/")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [] }) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ ticker: "SPY", timeframe: "5m", bars: [] }) });
}) as never;

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("MarketTickerPage", () => {
  it("renders chart, chain, and news for given ticker", async () => {
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/market/SPY"]}>
          <Routes>
            <Route path="/market/:ticker" element={<MarketTickerPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText(/SPY/)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 22.2: Run test to verify failure**

```bash
docker compose exec frontend npx vitest run src/__tests__/MarketTickerPage.test.tsx
```
Expected: ERROR — page missing.

- [ ] **Step 22.3: Implement page**

`frontend/src/pages/MarketTickerPage.tsx`:
```typescript
import { useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Chart from "../components/Chart";
import ChartCaptureButton from "../components/ChartCaptureButton";
import OptionChainTable from "../components/OptionChainTable";
import NewsFeed from "../components/NewsFeed";

export default function MarketTickerPage() {
  const { ticker = "SPY" } = useParams<{ ticker: string }>();
  const [params] = useSearchParams();
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "120");
  const chartContainer = useRef<HTMLDivElement | null>(null);

  const { data: chain } = useQuery({
    queryKey: ["chain", ticker],
    queryFn: () => fetch(`/api/market/chain/?ticker=${ticker}`).then((r) => r.json()),
  });

  const { data: news } = useQuery({
    queryKey: ["news", ticker],
    queryFn: () => fetch(`/api/market/news/?tickers=${ticker}`).then((r) => r.json()),
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 16 }}>
      <h1 style={{ margin: 0 }}>{ticker.toUpperCase()}</h1>

      <div ref={chartContainer} style={{ position: "relative", height: 400, background: "#0a0a0a" }}>
        <Chart ticker={ticker} timeframe={timeframe} bars={bars} />
        <ChartCaptureButton targetRef={chartContainer} caption={`${ticker} ${timeframe}, ${bars} bars`} />
      </div>

      <section>
        <h2 style={{ fontSize: 16, margin: "8px 0" }}>Option chain</h2>
        <OptionChainTable payload={chain ?? null} />
      </section>

      <section>
        <h2 style={{ fontSize: 16, margin: "8px 0" }}>News</h2>
        <NewsFeed items={news?.items ?? []} />
      </section>
    </div>
  );
}
```

- [ ] **Step 22.4: Wire route in `App.tsx`**

```typescript
import MarketTickerPage from "./pages/MarketTickerPage";
// inside <Routes>:
<Route path="/market/:ticker" element={<MarketTickerPage />} />
```

- [ ] **Step 22.5: Run test, expect green**

```bash
docker compose exec frontend npx vitest run src/__tests__/MarketTickerPage.test.tsx
```
Expected: 1 passed.

- [ ] **Step 22.6: Commit**

```bash
git add frontend/src/pages/MarketTickerPage.tsx frontend/src/App.tsx frontend/src/__tests__/MarketTickerPage.test.tsx
git commit -m "feat(frontend): /market/:ticker page (chart + chain + news, capture button)"
```

---

## Task 23: Snapshot composer extension (chain/news/image checkboxes + staged thumbnails)

**Files:**
- Modify: `frontend/src/pages/SnapshotComposerPage.tsx`

The composer's section list needs three new checkboxes (`chain`, `news`, `image`); a thumbnail strip below shows staged client captures from localStorage with × to drop. On capture, image IDs are sent in the snapshot create payload and localStorage is cleared.

- [ ] **Step 23.1: Read the existing composer**

```bash
docker compose exec frontend cat src/pages/SnapshotComposerPage.tsx | head -80
```

- [ ] **Step 23.2: Add the three checkboxes + staged image strip**

Edit `frontend/src/pages/SnapshotComposerPage.tsx`. Find the section-includes checkbox list (it will already have entries like `quotes`, `ohlc`, `positions`, `breadth`, `notes`). Append three more options to the same source-of-truth array:

```typescript
const SECTION_OPTIONS = [
  { key: "quotes", label: "Quotes" },
  { key: "ohlc", label: "OHLC" },
  { key: "positions", label: "Positions" },
  { key: "breadth", label: "Market breadth" },
  { key: "notes", label: "Notes" },
  { key: "chain", label: "Option chain" },
  { key: "news", label: "News" },
  { key: "image", label: "Charts (server-render)" },
];
```

(If the existing options live differently, integrate `chain`/`news`/`image` into the same shape. Do not duplicate.)

Add staged-thumbnails strip near the bottom of the form, above the Capture button:

```typescript
const [stagedIds, setStagedIds] = useState<number[]>(() => {
  try { return JSON.parse(localStorage.getItem("staged_image_ids") || "[]"); }
  catch { return []; }
});

function dropStaged(id: number) {
  const next = stagedIds.filter((x) => x !== id);
  setStagedIds(next);
  localStorage.setItem("staged_image_ids", JSON.stringify(next));
}

// in JSX:
{stagedIds.length > 0 && (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
    {stagedIds.map((id) => (
      <div key={id} style={{ position: "relative", border: "1px solid #333", borderRadius: 4 }}>
        <img src={`/api/snapshots/images/${id}/`} alt={`staged ${id}`}
             style={{ height: 60, width: "auto", display: "block" }} />
        <button
          type="button"
          onClick={() => dropStaged(id)}
          aria-label={`drop staged image ${id}`}
          style={{
            position: "absolute", top: -8, right: -8, width: 18, height: 18,
            borderRadius: 9, background: "#400", color: "#fff", border: "1px solid #800",
            cursor: "pointer", lineHeight: "16px", fontSize: 12, padding: 0,
          }}
        >×</button>
      </div>
    ))}
  </div>
)}
```

In the snapshot create POST body, include `image_ids: stagedIds`. After a successful POST, clear localStorage:
```typescript
localStorage.removeItem("staged_image_ids");
setStagedIds([]);
```

- [ ] **Step 23.3: Wire `image_ids` on the backend**

In `backend/apps/snapshots/views.py` `SnapshotViewSet.create`, after `Snapshot.objects.create(...)`, attach staged images:
```python
        image_ids = data.get("image_ids") or []
        if image_ids:
            from apps.snapshots.models import SnapshotImage
            SnapshotImage.objects.filter(id__in=image_ids, snapshot__isnull=True).update(snapshot=snap)
```

- [ ] **Step 23.4: Run frontend lint + tests**

```bash
docker compose exec frontend npm run lint
docker compose exec frontend npm test -- --run
```
Expected: no new errors / all tests pass.

- [ ] **Step 23.5: Commit**

```bash
git add frontend/src/pages/SnapshotComposerPage.tsx backend/apps/snapshots/views.py
git commit -m "feat(snapshots): composer adds chain/news/image checkboxes + staged image attach"
```

---

## Task 24: Worker Dockerfile — `worker-base` target with Playwright

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `pyproject.toml` (add `playwright` dep)

- [ ] **Step 24.1: Read current Dockerfile + pyproject**

```bash
cat backend/Dockerfile | head -60
grep -n playwright pyproject.toml
```

- [ ] **Step 24.2: Add `playwright` to deps**

In `pyproject.toml`, in the `[project]` `dependencies` list:
```toml
"playwright>=1.45,<2.0",
```

- [ ] **Step 24.3: Add `worker-base` build stage**

Append to `backend/Dockerfile` (after the existing final stage; assume it's named `runtime` — verify name first):
```dockerfile
###### worker-base (extends runtime; adds Playwright + chromium for chart rendering) ######
FROM runtime AS worker-base

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
        libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN /app/.venv/bin/playwright install chromium --with-deps
```

(If the Dockerfile's runtime stage isn't named `runtime`, use the actual final stage name. If there's no named final stage, add `AS runtime` to it.)

- [ ] **Step 24.4: Point worker service at the new target**

In `compose.yaml`, in the `worker` service `build:` block:
```yaml
worker:
  build:
    context: .
    dockerfile: backend/Dockerfile
    target: worker-base
```

- [ ] **Step 24.5: Build worker image**

```bash
docker compose build worker
```
Expected: builds successfully (~3–5 min). Look for `chromium` install step finishing without error.

- [ ] **Step 24.6: Verify Playwright loads in worker**

```bash
docker compose up -d worker
docker compose exec worker python -c "from playwright.sync_api import sync_playwright; print('OK')"
```
Expected: prints `OK`.

- [ ] **Step 24.7: Commit**

```bash
git add backend/Dockerfile pyproject.toml compose.yaml
git commit -m "feat(infra): worker-base image target with Playwright + chromium"
```

---

## Task 25: `RENDER_BASE_URL` setting

**Files:**
- Modify: `backend/config/settings/base.py`
- Modify: `backend/config/settings/dev.py`
- Modify: `backend/config/settings/prod.py`

- [ ] **Step 25.1: Add setting**

In `backend/config/settings/base.py`, add:
```python
RENDER_BASE_URL = os.environ.get("RENDER_BASE_URL", "http://frontend:5173")
```

In `backend/config/settings/dev.py`: leave default (`http://frontend:5173`).

In `backend/config/settings/prod.py`: override with hash-mode prod URL:
```python
RENDER_BASE_URL = os.environ.get("RENDER_BASE_URL", "http://web:8000/static/index.html")
```

- [ ] **Step 25.2: Smoke check**

```bash
docker compose exec web python -c "from django.conf import settings; print(settings.RENDER_BASE_URL)"
```
Expected: `http://frontend:5173`.

- [ ] **Step 25.3: Commit**

```bash
git add backend/config/settings/base.py backend/config/settings/dev.py backend/config/settings/prod.py
git commit -m "feat(infra): RENDER_BASE_URL setting (dev=frontend:5173, prod=hash route)"
```

---

## Task 26: Real `render_chart_png` Playwright implementation

**Files:**
- Modify: `backend/apps/snapshots/services/render.py`
- Test: `backend/apps/snapshots/tests/test_render_chart.py` (integration, marked, optional)

- [ ] **Step 26.1: Write integration test (marker-skipped by default)**

`backend/apps/snapshots/tests/test_render_chart.py`:
```python
import pytest

playwright = pytest.importorskip("playwright")
from apps.snapshots.models import SnapshotImage  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_render_chart_png_returns_real_png_bytes(settings):
    """Requires the worker image with chromium, and the frontend service running.

    Skip locally with: pytest -m 'not integration'.
    """
    from apps.snapshots.services.render import render_chart_png

    settings.RENDER_BASE_URL = "http://frontend:5173"
    img = render_chart_png("SPY", "5m", 10, snapshot_id=None)

    assert isinstance(img, SnapshotImage)
    assert bytes(img.data).startswith(b"\x89PNG")
```

Add `integration` marker to `pyproject.toml` `[tool.pytest.ini_options]`:
```toml
markers = [
    "integration: requires live external services (Playwright + frontend)",
]
```
(If `markers` already present, append the entry.)

Also update `pytest.ini` if it exists with the same marker (per CLAUDE.md "Tool config is duplicated").

- [ ] **Step 26.2: Replace stub with real implementation**

`backend/apps/snapshots/services/render.py`:
```python
"""Server-side chart rendering via Playwright."""
from __future__ import annotations

from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from django.conf import settings

from apps.snapshots.models import SnapshotImage


def _build_url(ticker: str, timeframe: str, bars: int) -> str:
    base = settings.RENDER_BASE_URL.rstrip("/")
    qs = urlencode({"ticker": ticker, "timeframe": timeframe, "bars": bars})
    if base.endswith(".html") or "/static/" in base:
        return f"{base}#/render/chart?{qs}"  # prod hash route
    return f"{base}/render/chart?{qs}"  # dev path route


async def _render_async(url: str) -> bytes:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page(viewport={"width": 1200, "height": 700})
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_selector("body[data-render-ready='true']", timeout=15000)
            chart = await page.locator("#chart-root").element_handle()
            assert chart is not None
            return await chart.screenshot(type="png")
        finally:
            await browser.close()


def render_chart_png(
    ticker: str, timeframe: str, bars: int, *, snapshot_id: int | None,
) -> SnapshotImage:
    url = _build_url(ticker, timeframe, bars)
    png = async_to_sync(_render_async)(url)
    return SnapshotImage.objects.create(
        snapshot_id=snapshot_id,
        kind="server_render",
        data=png,
        caption=f"{ticker} {timeframe}, {bars} bars",
    )
```

- [ ] **Step 26.3: Run the integration test against the live stack**

```bash
docker compose up -d
docker compose exec worker pytest backend/apps/snapshots/tests/test_render_chart.py -v -m integration
```
Expected: 1 passed (rendered PNG bytes start with PNG magic).

- [ ] **Step 26.4: Run the full backend suite, expect green and integration skipped**

```bash
docker compose exec web pytest -q
```
Expected: all green; integration test skipped or passed depending on env.

- [ ] **Step 26.5: Commit**

```bash
git add backend/apps/snapshots/services/render.py backend/apps/snapshots/tests/test_render_chart.py \
        pyproject.toml pytest.ini
git commit -m "feat(snapshots): Playwright render_chart_png against /render/chart"
```

---

## Task 27: End-to-end smoke test — full capture with all M5 sections

**Files:**
- Test: `backend/apps/snapshots/tests/test_capture_e2e_m5.py`

- [ ] **Step 27.1: Write the integration smoke**

`backend/apps/snapshots/tests/test_capture_e2e_m5.py`:
```python
"""Capture a snapshot that includes every M5 section type and assert payloads.

External calls to Schwab / Finnhub / Playwright are mocked at the SDK boundary.
"""
from unittest.mock import patch

import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import SnapshotImage
from apps.snapshots.services import capture


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.mark.django_db
def test_full_m5_capture_emits_all_sections():
    profile = TradingProfile.objects.create(name="P", style_text="x")

    fake_chain = {"ticker": "SPY", "underlying_last": "521.30",
                  "expiries": {"2026-04-25": {"calls": [], "puts": []}}}
    fake_news = [{"id": 1, "headline": "Fed", "summary": "x", "url": "https://x",
                  "source": "R", "datetime": 1700000000, "related": "SPY"}]

    def fake_render(ticker, timeframe, bars, *, snapshot_id):
        return SnapshotImage.objects.create(
            snapshot_id=snapshot_id, kind="server_render",
            data=PNG, caption=f"{ticker} {timeframe}",
        )

    with patch("apps.market.services.chain.fetch_chain", return_value=fake_chain), \
         patch("apps.market.services.news.fetch_news", return_value=fake_news), \
         patch("apps.snapshots.services.render.render_chart_png", side_effect=fake_render), \
         patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 521.3}}), \
         patch("apps.snapshots.services.fetch_ohlc", return_value=[]), \
         patch("apps.snapshots.services.fetch_positions", return_value=[]), \
         patch("apps.snapshots.services.fetch_market_context", return_value={}):
        snap = capture(
            profile=profile, objective="full m5",
            includes=["quotes", "ohlc", "positions", "breadth", "chain", "news", "image", "notes"],
            watchlist_tickers=["SPY"],
            ohlc_ticker="SPY", ohlc_timeframe="5m", ohlc_bars=60,
        )

    assert snap.status == "ready"
    kinds = {s.kind: s.status for s in snap.sections.all()}
    for k in ["quotes", "ohlc", "positions", "breadth", "chain", "news", "image", "notes"]:
        assert kinds.get(k) == "done", f"section {k} not done: {kinds}"
```

- [ ] **Step 27.2: Run and expect green**

```bash
docker compose exec web pytest backend/apps/snapshots/tests/test_capture_e2e_m5.py -v
```
Expected: 1 passed.

- [ ] **Step 27.3: Commit**

```bash
git add backend/apps/snapshots/tests/test_capture_e2e_m5.py
git commit -m "test(snapshots): end-to-end capture covering every M5 section type"
```

---

## Task 28: Smoke verification + cold rebuild + tag m5

- [ ] **Step 28.1: Full lint + test**

```bash
make check
```
Expected: ruff + mypy + pytest + frontend tests + lint all green.

- [ ] **Step 28.2: Smoke endpoints + routes**

```bash
docker compose up -d
sleep 10

# Backend endpoints (chain/news will return 503 without Schwab/Finnhub creds — that's expected)
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/market/chain/?ticker=SPY"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/market/news/?tickers=SPY"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/api/snapshots/images/?staged=true"

# Frontend routes
for path in "/" "/profiles" "/snapshot" "/threads" "/settings" "/watchlists" "/costs" "/market/SPY" "/render/chart?ticker=SPY&timeframe=5m&bars=10"; do
  printf "%-50s " "$path"
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:5173$path"
done
```
Expected: all 2xx or 503 (Schwab-not-connected for chain).

- [ ] **Step 28.3: Cold rebuild**

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 60
curl -s http://localhost:8000/api/health/
docker compose exec web pytest -q --tb=no 2>&1 | tail -5
docker compose exec frontend npm test -- --run 2>&1 | tail -5
```
Expected: all green.

- [ ] **Step 28.4: Update CLAUDE.md with M5 notes**

In the "Daily commands" table, no change needed. In the architecture/non-obvious section, add:

```markdown
- **Worker container has chromium for Playwright.** Cold-builds the worker image are ~3–5min slower because of the chromium download. The `web` and `beat` services use the smaller `runtime` target.
- **Render route `/render/chart`** is deterministic (URL params fully specify the render). Used by `snapshots.services.render.render_chart_png` to capture chart PNGs. In dev hits `http://frontend:5173/render/chart?...`; in prod uses hash routing on `index.html`.
```

Also update the milestone roadmap pointer: M4 → M5 done.

- [ ] **Step 28.5: Tag**

```bash
git add CLAUDE.md
git commit -m "docs: M5 (chains+news+images) carry-over notes" || echo "nothing to commit"
git tag -a m5-chains-news-images -m "M5: option chain + Finnhub news + client capture + Playwright server render"
git tag -l
```

Expected: tag `m5-chains-news-images` listed alongside `m1-skeleton`, `m2-market-data`, `m3-snapshots-ai`, `m4-full-threads`.

## Done

Next: **M6 — Observer** (ObserverSchedule, beat integration, observer timeline UI).
