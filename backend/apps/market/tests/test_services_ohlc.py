from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.ohlc import fetch_ohlc


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
