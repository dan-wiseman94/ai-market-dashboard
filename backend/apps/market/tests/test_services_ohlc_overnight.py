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
