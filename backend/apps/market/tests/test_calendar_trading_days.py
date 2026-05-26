from datetime import UTC, datetime

from apps.market.calendar.sessions import add_trading_days, session_close_on


def test_add_trading_days_skips_weekend():
    # Fri 2026-04-17 + 1 trading day = Mon 2026-04-20
    fri = datetime(2026, 4, 17, 14, 0, tzinfo=UTC)
    nxt = add_trading_days("us_equity", fri, 1)
    assert nxt.date() == datetime(2026, 4, 20).date()


def test_add_trading_days_skips_holiday():
    # Fri 2026-05-22 + 1 trading day skips Memorial Day (Mon 5/25) -> Tue 5/26
    fri = datetime(2026, 5, 22, 14, 0, tzinfo=UTC)
    nxt = add_trading_days("us_equity", fri, 1)
    assert nxt.date() == datetime(2026, 5, 26).date()


def test_crypto_counts_every_day():
    sat = datetime(2026, 4, 18, 0, 0, tzinfo=UTC)
    nxt = add_trading_days("crypto", sat, 1)
    assert nxt.date() == datetime(2026, 4, 19).date()


def test_session_close_on_regular_day():
    close = session_close_on("us_equity", datetime(2026, 4, 15).date())
    assert close is not None
    assert close.hour == 20  # 16:00 ET (EDT) == 20:00 UTC


def test_session_close_on_half_day_is_early():
    close = session_close_on("us_equity", datetime(2026, 11, 27).date())
    assert close is not None
    assert close.hour == 18  # 13:00 ET (EST) == 18:00 UTC


def test_session_close_on_non_trading_day_is_none():
    assert session_close_on("us_equity", datetime(2026, 4, 18).date()) is None  # Saturday
