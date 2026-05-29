from unittest.mock import patch

from apps.market.services.overnight import overnight_board


def test_board_groups_symbols_and_drops_unquoted():
    # fetch_quotes returns only the symbols Schwab quoted (others already dropped upstream).
    fake = {
        "/ES": {"last": 5000.0, "gap_pct": 0.5},
        "/VX": {"last": 14.0, "gap_pct": -1.0},
        "$DAX": {"last": 18000.0, "gap_pct": 0.2},
    }
    with patch("apps.market.services.overnight.fetch_quotes", return_value=fake) as fq:
        board = overnight_board()
    # gap context must be requested
    assert fq.call_args.kwargs.get("gap_context") is True
    assert board["futures"]["/ES"]["last"] == 5000.0
    assert board["vol_rates"]["/VX"]["gap_pct"] == -1.0
    assert board["overseas"]["$DAX"]["last"] == 18000.0
    # Symbols Schwab didn't quote (e.g. /NQ) simply don't appear.
    assert "/NQ" not in board["futures"]


def test_board_empty_groups_when_nothing_quoted():
    with patch("apps.market.services.overnight.fetch_quotes", return_value={}):
        board = overnight_board()
    assert board == {"futures": {}, "vol_rates": {}, "overseas": {}}
