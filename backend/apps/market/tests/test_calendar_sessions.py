# backend/apps/market/tests/test_calendar_sessions.py
from freezegun import freeze_time

from apps.market.calendar.sessions import MarketState, is_open, market_state


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET — NYSE open
def test_regular_session_open():
    st = market_state(market="us_equity")
    assert isinstance(st, MarketState)
    assert st.is_open is True
    assert st.phase == "open"
    assert st.is_early_close is False


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_weekend_closed():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "weekend"
    assert st.next_open is not None


@freeze_time("2026-05-25 14:00:00")  # Memorial Day (last Mon of May) — NYSE closed
def test_holiday_closed():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "holiday"


@freeze_time("2026-11-27 18:30:00")  # Fri after Thanksgiving, 13:30 ET — past 13:00 early close
def test_half_day_after_early_close():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.is_early_close is True


@freeze_time("2026-11-27 16:00:00")  # 11:00 ET — open on a half day
def test_half_day_open_before_early_close():
    st = market_state(market="us_equity")
    assert st.is_open is True
    assert st.is_early_close is True


@freeze_time("2026-05-27 12:00:00")  # Wed 08:00 ET — before the 09:30 open, after 04:00 pre
def test_premarket_phase():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "premarket"
    assert st.next_open is not None  # the 09:30 regular open is still ahead


@freeze_time("2026-05-27 22:00:00")  # Wed 18:00 ET — after the 16:00 close, before 20:00 post
def test_postmarket_phase():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "postmarket"


@freeze_time("2026-05-27 03:00:00")  # Wed 23:00 ET (prev day) — past 20:00 post, before 04:00 pre
def test_overnight_outside_extended_is_closed():
    st = market_state(market="us_equity")
    assert st.is_open is False
    assert st.phase == "closed"


@freeze_time("2026-05-27 12:00:00")  # NYSE premarket time; crypto has no pre/post → stays open
def test_extended_hours_only_for_markets_that_define_them():
    crypto = market_state(market="crypto")
    assert crypto.is_open is True
    assert crypto.phase == "open"


@freeze_time("2026-04-18 14:00:00")  # Saturday — crypto still open
def test_crypto_always_open():
    assert is_open(symbol="BTC-USD") is True
    assert is_open(symbol="SPY") is False


@freeze_time("2026-04-15 14:00:00")
def test_to_json_is_iso_serializable():
    st = market_state(market="us_equity")
    d = st.to_json()
    assert d["is_open"] is True
    assert isinstance(d["session_close"], str)  # ISO string
    assert d["market_key"] == "us_equity"
