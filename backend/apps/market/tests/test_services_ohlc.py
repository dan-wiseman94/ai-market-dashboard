from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.ohlc import (
    _session_window,
    fetch_ohlc,
    fetch_ohlc_session,
)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.mark.django_db
def test_fetch_ohlc_1m_calls_schwab_price_history():
    # Schwab's price-history endpoint returns {"candles": [{open, high, low, close, volume, datetime}, ...]}
    resp = MagicMock()
    resp.json.return_value = {
        "candles": [
            {
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 1000,
                "datetime": 1700000000000,
            },
            {
                "open": 100.5,
                "high": 101.5,
                "low": 100,
                "close": 101,
                "volume": 1200,
                "datetime": 1700000060000,
            },
        ]
    }
    client = MagicMock()
    client.get_price_history_every_minute.return_value = resp

    with patch("apps.market.services.ohlc.get_schwab_client", return_value=client):
        bars = fetch_ohlc("SPY", timeframe="1m", bars=60)

    assert len(bars) == 2
    assert bars[0]["open"] == 100
    assert bars[0]["ts"]  # ISO timestamp
    client.get_price_history_every_minute.assert_called_once()


@pytest.mark.django_db
def test_fetch_ohlc_invalid_timeframe_raises():
    with pytest.raises(ValueError):
        fetch_ohlc("SPY", timeframe="3m", bars=60)


# ── session-window fetch (full trading day + 1h premarket) ──────────────────

# 2026-05-28 is a regular Thursday NYSE session (EDT, UTC-4):
#   regular open  09:30 ET = 13:30 UTC
#   regular close 16:00 ET = 20:00 UTC
#   premarket-1h  08:30 ET = 12:30 UTC
_OPEN_M1H = datetime(2026, 5, 28, 12, 30, tzinfo=UTC)
_CLOSE = datetime(2026, 5, 28, 20, 0, tzinfo=UTC)


def test_session_window_after_close_spans_full_day_plus_premarket():
    win = _session_window("SPY", premarket_minutes=60, at=datetime(2026, 5, 28, 21, 0, tzinfo=UTC))
    assert win == (_OPEN_M1H, _CLOSE)


def test_session_window_midsession_caps_end_at_now():
    now = datetime(2026, 5, 28, 15, 0, tzinfo=UTC)  # 11:00 ET, mid-session
    assert _session_window("SPY", premarket_minutes=60, at=now) == (_OPEN_M1H, now)


def test_session_window_weekend_uses_most_recent_session():
    # Saturday 2026-05-30 → most recent session is Friday 2026-05-29.
    win = _session_window("SPY", premarket_minutes=60, at=datetime(2026, 5, 30, 15, 0, tzinfo=UTC))
    assert win == (
        datetime(2026, 5, 29, 12, 30, tzinfo=UTC),
        datetime(2026, 5, 29, 20, 0, tzinfo=UTC),
    )


@pytest.mark.django_db
def test_fetch_ohlc_session_requests_extended_hours_and_clamps_window():
    in_window = int(datetime(2026, 5, 28, 14, 0, tzinfo=UTC).timestamp() * 1000)
    out_of_window = int(datetime(2026, 5, 28, 23, 0, tzinfo=UTC).timestamp() * 1000)  # post-close
    resp = MagicMock()
    resp.json.return_value = {
        "candles": [
            {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "datetime": in_window},
            {"open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 10, "datetime": out_of_window},
        ]
    }
    client = MagicMock()
    client.get_price_history_every_minute.return_value = resp

    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch(
            "apps.market.services.ohlc._session_window",
            return_value=(_OPEN_M1H, _CLOSE),
        ),
    ):
        bars = fetch_ohlc_session("SPY", timeframe="1m")

    # Out-of-window candle is clamped away.
    assert len(bars) == 1
    _, kwargs = client.get_price_history_every_minute.call_args
    assert kwargs["need_extended_hours_data"] is True
    assert kwargs["start_datetime"] == _OPEN_M1H
    assert kwargs["end_datetime"] == _CLOSE


@pytest.mark.django_db
def test_fetch_ohlc_session_empty_when_no_session():
    client = MagicMock()
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._session_window", return_value=None),
    ):
        assert fetch_ohlc_session("SPY", timeframe="1m") == []
    client.get_price_history_every_minute.assert_not_called()


@pytest.mark.django_db
def test_fetch_ohlc_persists_bars():
    """Fetched bars must land in OHLCBar so the trigger backtest has data to replay."""
    from apps.market.models import OHLCBar

    resp = MagicMock()
    resp.json.return_value = {
        "candles": [
            {
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 1000,
                "datetime": 1700000000000,
            },
            {
                "open": 100.5,
                "high": 101.5,
                "low": 100,
                "close": 101,
                "volume": 1200,
                "datetime": 1700000060000,
            },
        ]
    }
    client = MagicMock()
    client.get_price_history_every_minute.return_value = resp

    with patch("apps.market.services.ohlc.get_schwab_client", return_value=client):
        fetch_ohlc("SPY", timeframe="1m", bars=60)

    rows = list(OHLCBar.objects.filter(ticker="SPY", timeframe="1m").order_by("ts"))
    assert len(rows) == 2
    assert float(rows[0].close) == 100.5
    assert rows[0].volume == 1000


@pytest.mark.django_db
def test_persist_bars_is_idempotent_and_updates_on_conflict():
    from apps.market.models import OHLCBar
    from apps.market.services.ohlc import _persist_bars

    bar = {
        "open": 1,
        "high": 2,
        "low": 1,
        "close": 1.5,
        "volume": 10,
        "ts": "2026-01-01T00:00:00+00:00",
    }
    _persist_bars("AAA", "1d", [bar])
    _persist_bars("AAA", "1d", [bar])  # same (ticker, timeframe, ts) → no duplicate row
    assert OHLCBar.objects.filter(ticker="AAA", timeframe="1d").count() == 1

    revised = {**bar, "close": 9.9, "volume": 99}
    _persist_bars("AAA", "1d", [revised])  # same key, new values → update in place
    rows = list(OHLCBar.objects.filter(ticker="AAA", timeframe="1d"))
    assert len(rows) == 1
    assert float(rows[0].close) == 9.9
    assert rows[0].volume == 99
