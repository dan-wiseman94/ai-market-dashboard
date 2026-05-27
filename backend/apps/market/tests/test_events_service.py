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
