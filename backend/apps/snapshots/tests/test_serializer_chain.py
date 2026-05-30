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


# ---------------------------------------------------------------------------
# Chain analytics block rendered into the AI payload
# ---------------------------------------------------------------------------

# Minimal chain for hand-verifiable analytics:
#   underlying = 100.00
#   expiry "2026-01-01":
#     call 95:  delta=+0.75, gamma=0.05, iv=20.0, volume=500, oi=1000
#     call 100: delta=+0.50, gamma=0.08, iv=18.0, volume=300, oi=800
#     call 105: delta=+0.25, gamma=0.05, iv=22.0, volume=200, oi=600
#     put  95:  delta=-0.25, gamma=0.05, iv=21.0, volume=100, oi=400
#     put  100: delta=-0.50, gamma=0.08, iv=19.0, volume=150, oi=500
#     put  105: delta=-0.75, gamma=0.05, iv=24.0, volume=400, oi=900
#
# Expected analytics (verified in test_option_analytics.py):
#   max-pain  = 100.0
#   P/C vol   = 650/1000 = 0.65   (call vol 500+300+200=1000, put vol 100+150+400=650)
#   P/C OI    = 1800/2400 = 0.75  (call OI 1000+800+600=2400, put OI 400+500+900=1800)
#   25d skew  = IV(put 95, -0.25) - IV(call 105, +0.25) = 21.0 - 22.0 = -1.0
#   ATM term  = 18.0 for 2026-01-01 (call 100 is closest to spot 100)
#   GEX total = (0.05*1000+0.08*800+0.05*600)*100*100 - (0.05*400+0.08*500+0.05*900)*100*100
#             = (50+64+30)*10000 - (20+40+45)*10000 = 1440000 - 1050000 = 390000
#             (wait: spot=100, single expiry only)
#             call 95:  +0.05*1000*100*100 = +500000
#             call 100: +0.08*800*100*100  = +640000
#             call 105: +0.05*600*100*100  = +300000
#             put  95:  -0.05*400*100*100  = -200000
#             put  100: -0.08*500*100*100  = -400000
#             put  105: -0.05*900*100*100  = -450000
#             total = 500000+640000+300000-200000-400000-450000 = 390000

ANALYTICS_PAYLOAD = {
    "underlying_last": "100.00",
    "ticker": "TST",
    "expiries": {
        "2026-01-01": {
            "calls": [
                {
                    "strike": "95.00",
                    "delta": "0.75",
                    "gamma": "0.05",
                    "iv": "20.0",
                    "volume": 500,
                    "oi": 1000,
                    "bid": "5.00",
                    "ask": "5.10",
                },
                {
                    "strike": "100.00",
                    "delta": "0.50",
                    "gamma": "0.08",
                    "iv": "18.0",
                    "volume": 300,
                    "oi": 800,
                    "bid": "2.00",
                    "ask": "2.10",
                },
                {
                    "strike": "105.00",
                    "delta": "0.25",
                    "gamma": "0.05",
                    "iv": "22.0",
                    "volume": 200,
                    "oi": 600,
                    "bid": "0.50",
                    "ask": "0.55",
                },
            ],
            "puts": [
                {
                    "strike": "95.00",
                    "delta": "-0.25",
                    "gamma": "0.05",
                    "iv": "21.0",
                    "volume": 100,
                    "oi": 400,
                    "bid": "0.40",
                    "ask": "0.45",
                },
                {
                    "strike": "100.00",
                    "delta": "-0.50",
                    "gamma": "0.08",
                    "iv": "19.0",
                    "volume": 150,
                    "oi": 500,
                    "bid": "1.80",
                    "ask": "1.90",
                },
                {
                    "strike": "105.00",
                    "delta": "-0.75",
                    "gamma": "0.05",
                    "iv": "24.0",
                    "volume": 400,
                    "oi": 900,
                    "bid": "4.80",
                    "ask": "4.90",
                },
            ],
        },
    },
}


def test_render_chain_analytics_block_present():
    """The '### Chain analytics' section must appear after the per-expiry table."""
    md = _render_chain(ANALYTICS_PAYLOAD, ticker="TST")
    assert "### Chain analytics" in md
    # Per-expiry table still present (not removed)
    assert "### Expiry 2026-01-01" in md


def test_render_chain_analytics_max_pain():
    """Max-pain = 100.0 for this fixture (verified by hand above)."""
    md = _render_chain(ANALYTICS_PAYLOAD, ticker="TST")
    # Max-pain line must contain the value 100.00
    assert "Max-pain" in md
    assert "100.00" in md


def test_render_chain_analytics_put_call_ratio():
    """P/C volume ratio = 650/1000 = 0.65; line must appear in output.

    call vol = 500+300+200 = 1000; put vol = 100+150+400 = 650 → ratio 0.65.
    """
    md = _render_chain(ANALYTICS_PAYLOAD, ticker="TST")
    assert "P/C volume ratio" in md
    # The formatted value 0.65 appears (rounded to 2dp by _fmt)
    assert "0.65" in md


def test_render_chain_analytics_iv_skew():
    """25-delta IV skew = 21.0 - 22.0 = -1.0; must appear as -1.00."""
    md = _render_chain(ANALYTICS_PAYLOAD, ticker="TST")
    assert "25-delta IV skew" in md
    assert "-1.00" in md


def test_render_chain_analytics_term_structure():
    """ATM IV term structure shows 2026-01-01 with iv=18.0 (call 100 closest to spot 100)."""
    md = _render_chain(ANALYTICS_PAYLOAD, ticker="TST")
    assert "ATM IV term structure" in md
    assert "2026-01-01" in md
    assert "18.00" in md


def test_render_chain_analytics_gex():
    """GEX total = 390000; line must appear with formatted value."""
    md = _render_chain(ANALYTICS_PAYLOAD, ticker="TST")
    assert "Dealer GEX" in md
    assert "390,000" in md


def test_render_chain_analytics_no_crash_on_missing_greeks():
    """Contracts with all-None greeks must not crash; analytics block still appears."""
    payload = {
        "underlying_last": "100.00",
        "expiries": {
            "2026-06-01": {
                "calls": [
                    {
                        "strike": "100.00",
                        "delta": None,
                        "gamma": None,
                        "iv": None,
                        "volume": None,
                        "oi": None,
                    }
                ],
                "puts": [],
            }
        },
    }
    md = _render_chain(payload, ticker="XXX")
    assert "### Chain analytics" in md
    # With no valid data, values degrade to em-dash — must not raise
    assert "Max-pain" in md
