from apps.snapshots.diff import diff_sections


def test_positions_pl_delta():
    prev = {"positions": [{"symbol": "NVDA", "unrealized_pl": 100, "quantity": 10}]}
    curr = {"positions": [{"symbol": "NVDA", "unrealized_pl": 250, "quantity": 10}]}
    out = diff_sections(prev, curr)
    assert "NVDA" in out and "100" in out and "250" in out


def test_ohlc_last_change():
    prev = {"ohlc": {"ticker": "SPY", "bars": [{"close": 500}]}}
    curr = {"ohlc": {"ticker": "SPY", "bars": [{"close": 505}]}}
    assert "SPY" in diff_sections(prev, curr)


def test_diff_never_raises_on_garbage():
    assert isinstance(diff_sections({"chain": 123}, {"chain": None}), str)
