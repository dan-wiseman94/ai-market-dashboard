from apps.snapshots.serializer import _render_chain

CHAIN_PAYLOAD = {
    "underlying_last": "521.30",
    "expiries": {
        "2026-04-25": {
            "calls": [
                {
                    "strike": "515.00",
                    "bid": "7.20",
                    "ask": "7.30",
                    "delta": "0.72",
                    "iv": "18.4",
                    "volume": 1234,
                    "oi": 5678,
                    "gamma": "0.04",
                    "theta": "-0.12",
                    "vega": "0.18",
                    "last": "7.25",
                },
                {
                    "strike": "520.00",
                    "bid": "3.85",
                    "ask": "3.95",
                    "delta": "0.55",
                    "iv": "17.9",
                    "volume": 999,
                    "oi": 1111,
                    "gamma": "0.05",
                    "theta": "-0.13",
                    "vega": "0.20",
                    "last": "3.90",
                },
            ],
            "puts": [
                {
                    "strike": "515.00",
                    "bid": "0.95",
                    "ask": "1.00",
                    "delta": "-0.28",
                    "iv": "19.1",
                    "volume": 222,
                    "oi": 4444,
                    "gamma": "0.04",
                    "theta": "-0.10",
                    "vega": "0.18",
                    "last": "0.97",
                },
            ],
        },
    },
}


def test_render_chain_emits_per_expiry_table():
    md = _render_chain(CHAIN_PAYLOAD, ticker="SPY")
    assert "## Option chain — SPY" in md
    assert "underlying $521.30" in md
    assert "### Expiry 2026-04-25" in md
    # Both call and put for strike 515 appear in the same row
    assert "| 515.00 | 7.20 | 7.30 | 0.72 | 18.4 | 0.95 | 1.00 | -0.28 | 19.1 |" in md
    # Strike 520 has only a call → put cells are em-dashes
    assert "| 520.00 | 3.85 | 3.95 | 0.55 | 17.9 | — | — | — | — |" in md


def test_render_chain_handles_empty_payload():
    out = _render_chain({"underlying_last": None, "expiries": {}}, ticker="XXX")
    assert "_(no expiries)_" in out


def test_render_chain_preserves_zero_bid_does_not_emit_dash():
    """A 0 bid is real semantic info on illiquid options — must not be hidden as missing."""
    payload = {
        "underlying_last": "100.00",
        "expiries": {
            "2026-05-01": {
                "calls": [
                    {"strike": "100.00", "bid": "0.00", "ask": "0.05", "delta": "0.50", "iv": "0.0"}
                ],
                "puts": [],
            }
        },
    }
    md = _render_chain(payload, ticker="XYZ")
    # zero values render as their string, not em-dash
    assert "| 100.00 | 0.00 | 0.05 | 0.50 | 0.0 | — | — | — | — |" in md
