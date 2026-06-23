from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from apps.market.models import MarketEvent
from apps.market.services import events


def _soon(days: int) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


@pytest.mark.django_db
def test_fetch_earnings_parses_and_dedups():
    body = {
        "earningsCalendar": [
            {
                "symbol": "NVDA",
                "date": _soon(2),
                "hour": "amc",
                "epsEstimate": 0.84,
                "epsActual": None,
                "revenueEstimate": 2.6e10,
            },
        ]
    }
    with (
        patch("apps.market.services.events._finnhub_get", return_value=body),
        patch("apps.market.services.events._finnhub_api_key", return_value="k"),
        patch(
            "apps.market.services.events.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
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


@pytest.mark.django_db
def test_fetch_macro_filters_to_us_high_impact_allowlist():
    body = {
        "economicCalendar": [
            {
                "event": "CPI YoY",
                "country": "US",
                "impact": "high",
                "time": _soon(5) + " 12:30:00",
                "estimate": 3.1,
                "prev": 3.2,
                "actual": None,
            },
            {
                "event": "German CPI",
                "country": "DE",
                "impact": "high",
                "time": _soon(5) + " 06:00:00",
            },
            {
                "event": "Retail Inventories",
                "country": "US",
                "impact": "low",
                "time": _soon(6) + " 12:30:00",
            },
        ]
    }
    with (
        patch("apps.market.services.events._finnhub_get", return_value=body),
        patch("apps.market.services.events._finnhub_api_key", return_value="k"),
        patch(
            "apps.market.services.events.cache.get_or_fetch",
            side_effect=lambda key, *, ttl_seconds, fetcher: fetcher(),
        ),
    ):
        out = events.fetch_macro()
    kinds = {e.kind for e in out}
    assert kinds == {"cpi"}  # German + low-impact dropped


@pytest.mark.django_db
def test_upsert_macro_keeps_distinct_same_kind_same_day_events():
    # CPI YoY and Core CPI YoY both map to kind 'cpi' on the same day but are
    # distinct releases — the old kind:date external_id collided and kept one.
    rows = [
        {"event": "CPI YoY", "country": "US", "impact": "high", "time": "2026-07-15 12:30:00"},
        {"event": "Core CPI YoY", "country": "US", "impact": "high", "time": "2026-07-15 12:30:00"},
    ]
    out = events._upsert_macro(rows, source="finnhub")
    assert len(out) == 2
    assert MarketEvent.objects.filter(kind="cpi").count() == 2
    # idempotent: re-upserting the same rows updates in place, no duplicates
    events._upsert_macro(rows, source="finnhub")
    assert MarketEvent.objects.filter(kind="cpi").count() == 2


@pytest.mark.django_db
def test_fetch_macro_falls_back_to_seed_when_endpoint_empty():
    seed = [
        {
            "event": "FOMC Rate Decision",
            "country": "US",
            "impact": "high",
            "time": _soon(7) + " 18:00:00",
            "estimate": None,
            "prev": None,
            "actual": None,
        }
    ]
    with (
        patch("apps.market.services.events._finnhub_api_key", return_value=None),
        patch("apps.market.services.events.SEED_MACRO_EVENTS", seed),
    ):
        out = events.fetch_macro()
    assert len(out) == 1
    assert out[0].kind == "fomc"
    assert out[0].source == "seed"


@pytest.mark.django_db
def test_upcoming_events_reads_store_and_computes_days_until():
    from django.utils import timezone

    MarketEvent.objects.create(
        source="finnhub",
        external_id="EARN:NVDA:x",
        kind="earnings",
        ticker="NVDA",
        title="NVDA earnings",
        event_time=timezone.now() + timedelta(days=3),
        when_hint="amc",
        impact="high",
        detail={"eps_est": 0.84},
    )
    MarketEvent.objects.create(
        source="finnhub",
        external_id="CPI:y",
        kind="cpi",
        title="CPI",
        event_time=timezone.now() + timedelta(days=6),
        impact="high",
    )
    out = events.upcoming_events(["NVDA"], within_days=14)
    assert [e["ticker"] for e in out["earnings"]] == ["NVDA"]
    assert out["earnings"][0]["days_until"] == 3
    assert [m["kind"] for m in out["macro"]] == ["cpi"]


@pytest.mark.django_db
def test_upcoming_events_excludes_macro_when_disabled():
    from django.utils import timezone

    MarketEvent.objects.create(
        source="s",
        external_id="CPI:z",
        kind="cpi",
        title="CPI",
        event_time=timezone.now() + timedelta(days=2),
    )
    out = events.upcoming_events([], include_macro=False)
    assert out["macro"] == []
