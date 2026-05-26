import pytest

from apps.market.calendar.heuristics import classify


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("SPY", "us_equity"),
        ("aapl", "us_equity"),  # case-insensitive
        ("$VIX", "us_equity"),  # cash index quoted on equity hours
        ("TLT", "us_equity"),  # bond ETF follows equities
        ("/ES", "cme_futures"),
        ("ES", "cme_futures"),
        ("/NQ", "cme_futures"),
        ("/VX", "cfe_futures"),
        ("VX", "cfe_futures"),  # VIX future, not the cash index
        ("BTC-USD", "crypto"),
        ("eth-usdt", "crypto"),
        ("VOD.L", "lse"),
        ("7203.T", "jpx"),
        ("", "us_equity"),  # empty -> default, never raises
    ],
)
def test_classify(symbol, expected):
    assert classify(symbol) == expected
