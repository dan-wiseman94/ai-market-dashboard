from freezegun import freeze_time

from apps.market.calendar.sessions import any_market_open


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_any_open_true_when_crypto_present():
    assert any_market_open(["SPY", "BTC-USD"]) is True


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_any_open_false_when_all_equities():
    assert any_market_open(["SPY", "QQQ"]) is False


@freeze_time("2026-04-15 14:00:00")  # Wed 10:00 ET
def test_empty_defaults_to_us_equity_open():
    assert any_market_open([]) is True
