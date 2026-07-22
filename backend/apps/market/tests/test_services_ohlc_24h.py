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
def test_fetch_ohlc_24h_blends_5m_older_and_1m_fine_tail():
    # Mid-session capture: the 1m tail is capped at _FINE_WINDOW (4h), so the
    # boundary sits at end-4h — NOT at session open (a 23h futures session or a
    # premarket capture of yesterday's session would otherwise be all-1m).
    start = datetime(2026, 5, 27, 18, 0, tzinfo=UTC)
    end = datetime(2026, 5, 28, 18, 0, tzinfo=UTC)
    session_open = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)
    fine_start = datetime(2026, 5, 28, 14, 0, tzinfo=UTC)  # end - 4h, after open

    def five_min(*_a, **_k):
        r = MagicMock()
        r.json.return_value = {
            "candles": [
                _candle(datetime(2026, 5, 28, 12, 0, tzinfo=UTC), 1),  # older -> kept (5m)
                _candle(fine_start, 9),  # at boundary -> dropped (belongs to 1m)
            ]
        }
        return r

    def one_min(*_a, **_k):
        r = MagicMock()
        r.json.return_value = {
            "candles": [
                _candle(datetime(2026, 5, 28, 15, 0, tzinfo=UTC), 2),  # fine tail -> kept (1m)
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

    assert [b["close"] for b in bars] == [1, 2]  # 5m older, then 1m tail; boundary dropped
    _, k5 = client.get_price_history_every_five_minutes.call_args
    assert (k5["start_datetime"], k5["end_datetime"]) == (start, fine_start)
    _, k1 = client.get_price_history_every_minute.call_args
    assert (k1["start_datetime"], k1["end_datetime"]) == (fine_start, end)


@pytest.mark.django_db
def test_fetch_ohlc_24h_early_session_keeps_whole_session_fine():
    # Shortly after the open, end-4h predates the session open — the fine tail
    # snaps to the open and the whole (short) session stays at 1m.
    start = datetime(2026, 5, 27, 14, 30, tzinfo=UTC)
    end = datetime(2026, 5, 28, 14, 30, tzinfo=UTC)  # one hour into the session
    session_open = datetime(2026, 5, 28, 13, 30, tzinfo=UTC)

    resp5 = MagicMock()
    resp5.json.return_value = {"candles": [_candle(datetime(2026, 5, 28, 12, 0, tzinfo=UTC), 1)]}
    resp1 = MagicMock()
    resp1.json.return_value = {"candles": [_candle(datetime(2026, 5, 28, 14, 0, tzinfo=UTC), 2)]}
    client = MagicMock()
    client.get_price_history_every_five_minutes.return_value = resp5
    client.get_price_history_every_minute.return_value = resp1
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="1m")

    assert [b["close"] for b in bars] == [1, 2]
    _, k5 = client.get_price_history_every_five_minutes.call_args
    assert (k5["start_datetime"], k5["end_datetime"]) == (start, session_open)
    _, k1 = client.get_price_history_every_minute.call_args
    assert (k1["start_datetime"], k1["end_datetime"]) == (session_open, end)


@pytest.mark.django_db
def test_fetch_ohlc_24h_weekend_capture_coarsens_stale_session():
    # Weekend/pre-market: the window snapped back to Friday's open. Only the
    # last 4h stays 1m (dead air on a Saturday); Friday's session comes back 5m
    # instead of ~1,000 stale 1m bars.
    session_open = datetime(2026, 5, 29, 13, 30, tzinfo=UTC)
    start = session_open  # now-24h is after the session open -> snapped
    end = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    fine_start = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)  # end - 4h

    resp5 = MagicMock()
    resp5.json.return_value = {"candles": [_candle(datetime(2026, 5, 29, 14, 0, tzinfo=UTC), 2)]}
    resp1 = MagicMock()
    resp1.json.return_value = {"candles": []}
    client = MagicMock()
    client.get_price_history_every_five_minutes.return_value = resp5
    client.get_price_history_every_minute.return_value = resp1
    with (
        patch("apps.market.services.ohlc.get_schwab_client", return_value=client),
        patch("apps.market.services.ohlc._union_window", return_value=(start, end, session_open)),
    ):
        bars = fetch_ohlc_24h("SPY", timeframe="1m")

    assert [b["close"] for b in bars] == [2]
    _, k5 = client.get_price_history_every_five_minutes.call_args
    assert (k5["start_datetime"], k5["end_datetime"]) == (start, fine_start)
    _, k1 = client.get_price_history_every_minute.call_args
    assert (k1["start_datetime"], k1["end_datetime"]) == (fine_start, end)
