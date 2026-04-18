from apps.market.services.chain import _normalize_chain

SCHWAB_RESPONSE = {
    "underlyingPrice": 521.30,
    "callExpDateMap": {
        "2026-04-25:8": {
            "515.0": [{
                "strikePrice": 515.0, "bid": 7.20, "ask": 7.30, "last": 7.25,
                "totalVolume": 1234, "openInterest": 5678,
                "delta": 0.72, "gamma": 0.04, "theta": -0.12, "vega": 0.18,
                "volatility": 18.4,
            }],
            "520.0": [{
                "strikePrice": 520.0, "bid": 3.85, "ask": 3.95, "last": 3.90,
                "totalVolume": 999, "openInterest": 1111,
                "delta": 0.55, "gamma": 0.05, "theta": -0.13, "vega": 0.20,
                "volatility": 17.9,
            }],
        },
    },
    "putExpDateMap": {
        "2026-04-25:8": {
            "515.0": [{
                "strikePrice": 515.0, "bid": 0.95, "ask": 1.00, "last": 0.97,
                "totalVolume": 222, "openInterest": 4444,
                "delta": -0.28, "gamma": 0.04, "theta": -0.10, "vega": 0.18,
                "volatility": 19.1,
            }],
        },
    },
}


def test_normalize_chain_flattens_schwab_shape():
    out = _normalize_chain(SCHWAB_RESPONSE)
    assert out["underlying_last"] == "521.30"
    assert "2026-04-25" in out["expiries"]
    calls = out["expiries"]["2026-04-25"]["calls"]
    assert len(calls) == 2
    assert calls[0]["strike"] == "515.00"
    assert calls[0]["bid"] == "7.20"
    assert calls[0]["delta"] == "0.72"
    puts = out["expiries"]["2026-04-25"]["puts"]
    assert len(puts) == 1
    assert puts[0]["strike"] == "515.00"


def test_normalize_chain_handles_empty_maps():
    out = _normalize_chain({"underlyingPrice": 100.0, "callExpDateMap": {}, "putExpDateMap": {}})
    assert out["underlying_last"] == "100.00"
    assert out["expiries"] == {}


def test_normalize_chain_handles_schwab_sentinel_strings():
    """Schwab returns 'N/A' or '' for unavailable greeks; _fmt should return None, not crash."""
    raw = {
        "underlyingPrice": 100.0,
        "callExpDateMap": {
            "2026-05-01:14": {
                "100.0": [{
                    "strikePrice": 100.0, "bid": "N/A", "ask": "",
                    "delta": "--", "volatility": "N/A",
                }],
            },
        },
        "putExpDateMap": {},
    }
    out = _normalize_chain(raw)
    contract = out["expiries"]["2026-05-01"]["calls"][0]
    assert contract["strike"] == "100.00"
    assert contract["bid"] is None
    assert contract["ask"] is None
    assert contract["delta"] is None
    assert contract["iv"] is None


def test_normalize_chain_merges_duplicate_expiry_dates():
    """Schwab can return two DTE suffixes for the same calendar date — both sets of contracts must be preserved."""
    raw = {
        "underlyingPrice": 100.0,
        "callExpDateMap": {
            "2026-05-01:7": {
                "95.0": [{"strikePrice": 95.0, "bid": 5.0}],
            },
            "2026-05-01:8": {
                "100.0": [{"strikePrice": 100.0, "bid": 1.0}],
            },
        },
        "putExpDateMap": {},
    }
    out = _normalize_chain(raw)
    calls = out["expiries"]["2026-05-01"]["calls"]
    assert len(calls) == 2
    # sorted by strike
    assert calls[0]["strike"] == "95.00"
    assert calls[1]["strike"] == "100.00"
