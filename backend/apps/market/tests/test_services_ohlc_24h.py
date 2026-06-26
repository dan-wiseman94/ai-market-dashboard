from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.ohlc import _most_recent_session_open, _union_window


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


# 2026-05-28 is a regular Thursday NYSE session (EDT, UTC-4): open 13:30 UTC.
# 2026-05-29 is a regular Friday session: open 13:30 UTC. 2026-06-01 is the next Monday.
_THU_OPEN = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)
_FRI_OPEN = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)


def test_most_recent_session_open_after_close_is_todays_open():
    now = datetime(2026, 5, 28, 21, 0, tzinfo=UTC)  # Thu 17:00 ET, after close
    assert _most_recent_session_open("SPY", at=now) == _THU_OPEN


def test_most_recent_session_open_premarket_is_prior_session():
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)  # Fri 08:00 ET, before Fri open
    assert _most_recent_session_open("SPY", at=now) == _THU_OPEN


def test_union_window_midsession_is_rolling_24h():
    now = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)  # Thu 14:00 ET, mid-session
    start, end, session_open = _union_window("SPY", at=now)
    assert end == now
    assert session_open == _THU_OPEN
    assert start == now - timedelta(hours=24)  # 24h is before session open -> rolling


def test_union_window_stretches_back_to_session_over_weekend():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)  # Mon 08:00 ET, pre-market
    start, end, session_open = _union_window("SPY", at=now)
    assert session_open == _FRI_OPEN
    assert start == _FRI_OPEN  # now-24h (Sun) is after Fri open -> snaps back to session
    assert end == now


from apps.market.schwab_client import SchwabNotConnectedError  # noqa: E402
from apps.market.services.ohlc import fetch_ohlc_24h  # noqa: E402


@pytest.mark.django_db
def test_fetch_ohlc_24h_passes_union_window_and_clamps_extended_hours():
    start = datetime(2026, 5, 27, 18, 0, tzinfo=UTC)
    end = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)
    session_open = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)
    in_window = int(datetime(2026, 5, 28, 2, 0, tzinfo=UTC).timestamp() * 1000)
    out_of_window = int(datetime(2026, 5, 28, 19, 0, tzinfo=UTC).timestamp() * 1000)
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
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="5m")
    assert len(bars) == 1  # out-of-window candle clamped away
    _, kwargs = client.get_price_history_every_five_minutes.call_args
    assert kwargs["need_extended_hours_data"] is True
    assert kwargs["start_datetime"] == start
    assert kwargs["end_datetime"] == end


@pytest.mark.django_db
def test_fetch_ohlc_24h_returns_empty_when_no_window():
    with patch("apps.market.services.ohlc._union_window", return_value=None):
        assert fetch_ohlc_24h("SPY", timeframe="5m") == []


@pytest.mark.django_db
def test_fetch_ohlc_24h_falls_back_to_alt_bars_when_schwab_not_connected():
    with (
        patch(
            "apps.market.services.ohlc.get_schwab_client",
            side_effect=SchwabNotConnectedError(),
        ),
        patch(
            "apps.market.services.fallback.alt_bars",
            return_value=[{"ts": "x", "close": 9}],
        ) as alt,
    ):
        assert fetch_ohlc_24h("SPY", timeframe="5m") == [{"ts": "x", "close": 9}]
    alt.assert_called_once()
    assert alt.call_args.kwargs["limit"] == 288  # _ALT_24H_LIMIT["5m"]


def _candle(dt: datetime, close: float) -> dict:
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1,
        "datetime": int(dt.timestamp() * 1000),
    }


@pytest.mark.django_db
def test_fetch_ohlc_24h_blends_5m_older_and_1m_current_session():
    start = datetime(2026, 5, 27, 18, 0, tzinfo=UTC)
    end = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)
    session_open = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)

    def five_min(*_a, **_k):
        r = MagicMock()
        r.json.return_value = {
            "candles": [
                _candle(datetime(2026, 5, 28, 12, 0, tzinfo=UTC), 1),  # pre-session -> kept (5m)
                _candle(session_open, 9),  # at open -> dropped from series
            ]
        }
        return r

    def one_min(*_a, **_k):
        r = MagicMock()
        r.json.return_value = {
            "candles": [
                _candle(datetime(2026, 5, 28, 14, 0, tzinfo=UTC), 2),  # in session -> kept (1m)
            ]
        }
        return r

    client = MagicMock()
    client.get_price_history_every_five_minutes.side_effect = five_min
    client.get_price_history_every_minute.side_effect = one_min
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="1m")

    assert [b["close"] for b in bars] == [1, 2]  # 5m pre-session, then 1m session; boundary dropped
    _, k5 = client.get_price_history_every_five_minutes.call_args
    assert (k5["start_datetime"], k5["end_datetime"]) == (start, session_open)
    _, k1 = client.get_price_history_every_minute.call_args
    assert (k1["start_datetime"], k1["end_datetime"]) == (session_open, end)


@pytest.mark.django_db
def test_fetch_ohlc_24h_1m_no_older_segment_when_window_starts_at_session_open():
    session_open = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)
    start = session_open  # weekend/pre-market: now-24h is after the session open
    end = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    resp = MagicMock()
    resp.json.return_value = {"candles": [_candle(datetime(2026, 5, 29, 14, 0, tzinfo=UTC), 2)]}
    client = MagicMock()
    client.get_price_history_every_minute.return_value = resp
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="1m")
    assert [b["close"] for b in bars] == [2]
    client.get_price_history_every_five_minutes.assert_not_called()
