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


def test_diff_chain_reports_expiry_count_change():
    # Payload stores expiries as a dict keyed by date (NOT an "expirations" list).
    prev = {"chain": {"expiries": {"2026-01-16": {}, "2026-02-20": {}}}}
    curr = {"chain": {"expiries": {"2026-01-16": {}, "2026-02-20": {}, "2026-03-20": {}}}}
    out = diff_sections(prev, curr)
    assert "chain" in out.lower()
    assert "2 → 3" in out


def test_diff_chain_silent_when_expiry_count_unchanged():
    same = {"chain": {"expiries": {"2026-01-16": {}}}}
    assert "expiries:" not in diff_sections(same, {"chain": {"expiries": {"2026-01-16": {}}}})
