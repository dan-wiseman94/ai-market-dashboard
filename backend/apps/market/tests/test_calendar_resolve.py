from apps.market.calendar.resolve import calendar_for


def test_calendar_for_uses_heuristic():
    assert calendar_for("SPY") == "us_equity"
    assert calendar_for("BTC-USD") == "crypto"
    assert calendar_for("/ES") == "cme_futures"
