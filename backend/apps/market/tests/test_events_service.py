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
