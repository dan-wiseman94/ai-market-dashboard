import pytest

from apps.market.symbols import is_equity_like, normalize_symbol


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


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Bare CME future roots get Schwab's leading-slash futures namespace.
        ("ES", "/ES"),  # E-mini S&P 500
        ("es", "/ES"),  # case-insensitive
        (" es ", "/ES"),  # whitespace stripped
        ("NQ", "/NQ"),  # E-mini Nasdaq-100
        ("RTY", "/RTY"),  # E-mini Russell 2000
        ("YM", "/YM"),  # E-mini Dow
        ("CL", "/CL"),  # crude oil (future, not Colgate equity)
        ("GC", "/GC"),  # gold
        ("ZN", "/ZN"),  # 10y note
        # CFE / VIX future root.
        ("VX", "/VX"),
        # Already-prefixed futures symbols are idempotent.
        ("/ES", "/ES"),
        ("/es", "/ES"),
        ("/ESU24", "/ESU24"),  # dated contract passes through untouched
        # The cash VIX index ($VIX) stays distinct from the VIX future (/VX).
        ("VIX", "$VIX"),
    ],
)
def test_normalize_symbol_futures(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Plain stocks/ETFs are fine for equity-only providers.
        ("QQQ", True),
        ("AAPL", True),
        ("spy", True),
        (" xlk ", True),
        # Futures — bare root, slash-prefixed root, dated contract.
        ("ES", False),
        ("NQ", False),
        ("/NQ", False),
        ("/ESU26", False),
        ("VX", False),
        # Cash indices — bare alias and $-prefixed.
        ("SPX", False),
        ("$SPX", False),
        ("$VIX", False),
        # Empty / whitespace.
        ("", False),
        ("   ", False),
    ],
)
def test_is_equity_like(raw, expected):
    assert is_equity_like(raw) is expected
