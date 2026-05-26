from apps.market.calendar.resolve import calendar_for, clear_resolution_cache


def test_calendar_for_uses_heuristic():
    assert calendar_for("SPY") == "us_equity"
    assert calendar_for("BTC-USD") == "crypto"
    assert calendar_for("/ES") == "cme_futures"


def test_calendar_for_is_cached_and_clearable():
    clear_resolution_cache()
    assert calendar_for("SPY") == "us_equity"  # populates cache
    clear_resolution_cache()  # must not raise
    assert calendar_for("SPY") == "us_equity"
