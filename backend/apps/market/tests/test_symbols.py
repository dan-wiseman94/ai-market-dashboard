import pytest

from apps.market.symbols import normalize_symbol


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Bare index aliases get the Schwab "$" namespace.
        ("SPX", "$SPX"),
        ("spx", "$SPX"),
        (" spx ", "$SPX"),
        ("VIX", "$VIX"),
        ("NDX", "$NDX"),
        ("RUT", "$RUT"),
        ("DJI", "$DJI"),
        ("COMPX", "$COMPX"),
        ("OEX", "$OEX"),
        # Already-prefixed symbols are idempotent.
        ("$SPX", "$SPX"),
        ("$spx", "$SPX"),
        ("$VIX", "$VIX"),
        # ETFs and ordinary equities pass through (just upper-cased).
        ("SPY", "SPY"),
        ("QQQ", "QQQ"),
        ("aapl", "AAPL"),
        ("XLK", "XLK"),
        # Empty / whitespace.
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected
