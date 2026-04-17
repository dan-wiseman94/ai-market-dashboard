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
