from datetime import UTC, datetime, timedelta

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
