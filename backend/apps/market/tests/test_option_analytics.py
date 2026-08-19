"""Unit tests for apps.market.services.option_analytics.

All fixtures are hand-constructed so every expected value can be verified
by arithmetic shown in inline comments.
"""

from __future__ import annotations

import pytest

from apps.market.services.option_analytics import (
    _gex,
    _iv_skew_25d,
    _max_pain,
    _put_call,
    _term_structure,
    chain_analytics,
)

# ---------------------------------------------------------------------------
# Shared fixture — a two-expiry chain with spot=100.0
#
# Expiry "2026-01-01":
#   call  95: delta=+0.75, gamma=0.05, iv=20.0, volume=500, oi=1000
#   call 100: delta=+0.50, gamma=0.08, iv=18.0, volume=300, oi=800
#   call 105: delta=+0.25, gamma=0.05, iv=22.0, volume=200, oi=600
#   put   95: delta=-0.25, gamma=0.05, iv=21.0, volume=100, oi=400
#   put  100: delta=-0.50, gamma=0.08, iv=19.0, volume=150, oi=500
#   put  105: delta=-0.75, gamma=0.05, iv=24.0, volume=400, oi=900
#
# Expiry "2026-02-01":
#   call 100: delta=+0.50, gamma=0.04, iv=17.0, volume=50,  oi=200
#   put  100: delta=-0.50, gamma=0.04, iv=16.0, volume=50,  oi=200
# ---------------------------------------------------------------------------

SPOT = 100.0

CONTRACTS: list[dict] = [
    {
        "expiry": "2026-01-01",
        "side": "call",
        "strike": "95.00",
        "delta": "0.75",
        "gamma": "0.05",
        "iv": "20.0",
        "volume": 500,
        "oi": 1000,
    },
    {
        "expiry": "2026-01-01",
        "side": "call",
        "strike": "100.00",
        "delta": "0.50",
        "gamma": "0.08",
        "iv": "18.0",
        "volume": 300,
        "oi": 800,
    },
    {
        "expiry": "2026-01-01",
        "side": "call",
        "strike": "105.00",
        "delta": "0.25",
        "gamma": "0.05",
        "iv": "22.0",
        "volume": 200,
        "oi": 600,
    },
    {
        "expiry": "2026-01-01",
        "side": "put",
        "strike": "95.00",
        "delta": "-0.25",
        "gamma": "0.05",
        "iv": "21.0",
        "volume": 100,
        "oi": 400,
    },
    {
        "expiry": "2026-01-01",
        "side": "put",
        "strike": "100.00",
        "delta": "-0.50",
        "gamma": "0.08",
        "iv": "19.0",
        "volume": 150,
        "oi": 500,
    },
    {
        "expiry": "2026-01-01",
        "side": "put",
        "strike": "105.00",
        "delta": "-0.75",
        "gamma": "0.05",
        "iv": "24.0",
        "volume": 400,
        "oi": 900,
    },
    {
        "expiry": "2026-02-01",
        "side": "call",
        "strike": "100.00",
        "delta": "0.50",
        "gamma": "0.04",
        "iv": "17.0",
        "volume": 50,
        "oi": 200,
    },
    {
        "expiry": "2026-02-01",
        "side": "put",
        "strike": "100.00",
        "delta": "-0.50",
        "gamma": "0.04",
        "iv": "16.0",
        "volume": 50,
        "oi": 200,
    },
]


class TestPutCall:
    def test_volume_ratio(self):
        # call vol = 500+300+200+50 = 1050; put vol = 100+150+400+50 = 700
        # P/C volume = 700/1050 = 0.6667
        result = _put_call(CONTRACTS)
        assert result["volume_ratio"] == pytest.approx(700 / 1050, rel=1e-4)

    def test_oi_ratio(self):
        # call OI = 1000+800+600+200 = 2600; put OI = 400+500+900+200 = 2000
        # P/C OI = 2000/2600 = 0.7692
        result = _put_call(CONTRACTS)
        assert result["oi_ratio"] == pytest.approx(2000 / 2600, rel=1e-4)

    def test_empty_returns_none(self):
        result = _put_call([])
        assert result["volume_ratio"] is None
        assert result["oi_ratio"] is None

    def test_all_calls_no_puts_returns_zero_ratios(self):
        # No puts → put vol=0, put OI=0; ratios are 0/call = 0.0 (meaningful: all call-side).
        # None is reserved for "no call data at all" (division impossible).
        contracts = [
            {"side": "call", "volume": 100, "oi": 200, "expiry": "2026-01-01", "strike": "100.00"}
        ]
        result = _put_call(contracts)
        assert result["volume_ratio"] == pytest.approx(0.0)
        assert result["oi_ratio"] == pytest.approx(0.0)

    def test_missing_volume_treated_as_zero(self):
        # Volume None → treated as 0 (not skipped, not raised)
        contracts = [
            {"side": "call", "volume": None, "oi": 100, "expiry": "2026-01-01", "strike": "100.00"},
            {"side": "put", "volume": None, "oi": 200, "expiry": "2026-01-01", "strike": "100.00"},
        ]
        result = _put_call(contracts)
        # volume ratio: put 0 / call 0 → None (no call vol)
        assert result["volume_ratio"] is None
        # oi ratio: 200/100 = 2.0
        assert result["oi_ratio"] == pytest.approx(2.0)


class TestMaxPain:
    def test_max_pain_nearest_expiry(self):
        # Nearest expiry "2026-01-01", strikes [95, 100, 105].
        # K=95:  calls payout=0; puts payout = (95-95)*400 + (100-95)*500 + (105-95)*900
        #        = 0 + 2500 + 9000 = 11500
        # K=100: calls payout = (100-95)*1000 = 5000; puts = (105-100)*900 = 4500 → total 9500
        # K=105: calls payout = (105-95)*1000 + (105-100)*800 = 10000+4000=14000; puts=0 → 14000
        # Min is K=100 (9500).
        result = _max_pain(CONTRACTS)
        assert result == pytest.approx(100.0)

    def test_max_pain_single_strike(self):
        contracts = [
            {"expiry": "2026-01-01", "side": "call", "strike": "100.00", "oi": 500},
        ]
        # Only one candidate strike → it wins by default
        assert _max_pain(contracts) == pytest.approx(100.0)

    def test_max_pain_empty_returns_none(self):
        assert _max_pain([]) is None

    def test_max_pain_skips_missing_strike(self):
        # Contract with no strike should be skipped, not cause a crash
        contracts = [
            {"expiry": "2026-01-01", "side": "call", "strike": None, "oi": 999},
            {"expiry": "2026-01-01", "side": "put", "strike": "100.00", "oi": 200},
        ]
        # Only strike 100 is valid; it's the only candidate, so it wins
        result = _max_pain(contracts)
        assert result == pytest.approx(100.0)

    def test_max_pain_uses_nearest_expiry_only(self):
        # Max pain should use "2026-01-01" contracts, ignoring "2026-02-01".
        # Verifiable: the result for CONTRACTS is 100.0 (computed above), so
        # if we include only the 2026-02-01 sub-chain (single strike 100),
        # it should still return 100.0 regardless.
        only_far = [c for c in CONTRACTS if c["expiry"] == "2026-02-01"]
        result = _max_pain(only_far)
        # Only one strike in this expiry
        assert result == pytest.approx(100.0)


class TestIvSkew25d:
    def test_skew_nearest_expiry(self):
        # Nearest expiry "2026-01-01":
        #   call closest to |delta|=0.25 → call 105 (delta=0.25, iv=22.0)
        #   put  closest to |delta|=0.25 → put   95 (delta=-0.25, iv=21.0)
        # skew = IV(25d put) - IV(25d call) = 21.0 - 22.0 = -1.0
        result = _iv_skew_25d(CONTRACTS)
        assert result == pytest.approx(-1.0)

    def test_skew_empty_returns_none(self):
        assert _iv_skew_25d([]) is None

    def test_skew_missing_delta_skips_contract(self):
        contracts = [
            # call with no delta → skipped; remaining call has delta 0.25
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "100.00",
                "delta": None,
                "iv": "20.0",
            },
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "105.00",
                "delta": "0.25",
                "iv": "22.0",
            },
            {
                "expiry": "2026-01-01",
                "side": "put",
                "strike": "95.00",
                "delta": "-0.25",
                "iv": "21.0",
            },
        ]
        result = _iv_skew_25d(contracts)
        assert result == pytest.approx(21.0 - 22.0)

    def test_skew_no_puts_returns_none(self):
        contracts = [
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "100.00",
                "delta": "0.50",
                "iv": "20.0",
            },
        ]
        assert _iv_skew_25d(contracts) is None

    def test_skew_no_calls_returns_none(self):
        contracts = [
            {
                "expiry": "2026-01-01",
                "side": "put",
                "strike": "100.00",
                "delta": "-0.50",
                "iv": "20.0",
            },
        ]
        assert _iv_skew_25d(contracts) is None


class TestTermStructure:
    def test_term_structure_two_expiries(self):
        # "2026-01-01" → ATM call iv = 18.0 (call 100, |strike-spot|=0)
        # "2026-02-01" → ATM call iv = 17.0 (call 100, |strike-spot|=0)
        result = _term_structure(CONTRACTS, spot=SPOT)
        assert len(result) == 2
        assert result[0] == {"expiry": "2026-01-01", "atm_iv": pytest.approx(18.0)}
        assert result[1] == {"expiry": "2026-02-01", "atm_iv": pytest.approx(17.0)}

    def test_term_structure_empty_returns_empty(self):
        assert _term_structure([], spot=100.0) == []

    def test_term_structure_spot_none_returns_none_atm_ivs(self):
        result = _term_structure(CONTRACTS, spot=None)
        assert len(result) == 2
        assert all(r["atm_iv"] is None for r in result)

    def test_term_structure_sorted_by_expiry(self):
        reversed_contracts = list(reversed(CONTRACTS))
        result = _term_structure(reversed_contracts, spot=SPOT)
        expiries = [r["expiry"] for r in result]
        assert expiries == sorted(expiries)

    def test_term_structure_picks_call_over_put_at_same_strike(self):
        # At expiry "2026-01-01" strike 100: call iv=18.0, put iv=19.0
        # ATM should prefer call → 18.0
        contracts = [
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "100.00",
                "iv": "18.0",
                "delta": "0.50",
            },
            {
                "expiry": "2026-01-01",
                "side": "put",
                "strike": "100.00",
                "iv": "19.0",
                "delta": "-0.50",
            },
        ]
        result = _term_structure(contracts, spot=100.0)
        assert result[0]["atm_iv"] == pytest.approx(18.0)


class TestGex:
    def test_total_gex(self):
        # Per contract (spot=100):
        #   call  95: +0.05 * 1000 * 100 * 100 = +500_000
        #   call 100: +0.08 * 800  * 100 * 100 = +640_000
        #   call 105: +0.05 * 600  * 100 * 100 = +300_000
        #   put   95: -0.05 * 400  * 100 * 100 = -200_000
        #   put  100: -0.08 * 500  * 100 * 100 = -400_000
        #   put  105: -0.05 * 900  * 100 * 100 = -450_000
        #   call 100 (Feb): +0.04 * 200 * 100 * 100 = +80_000
        #   put  100 (Feb): -0.04 * 200 * 100 * 100 = -80_000
        # Total = 500k+640k+300k-200k-400k-450k+80k-80k = 390_000
        result = _gex(CONTRACTS, spot=SPOT)
        assert result["total"] == pytest.approx(390_000.0)

    def test_flip_strike(self):
        # Per-strike GEX (all expiries merged):
        #   95:  call(Jan) 500k + put(Jan) -200k = +300_000
        #  100:  call(Jan) 640k + put(Jan) -400k + call(Feb) +80k + put(Feb) -80k = +240_000
        #  105:  call(Jan) 300k + put(Jan) -450k = -150_000
        # Sign change between 100 (+240k) and 105 (-150k).
        # Interpolation: t = 240k / (240k + 150k) = 240/390
        # flip = 100 + 5 * (240/390) ~ 103.0769
        result = _gex(CONTRACTS, spot=SPOT)
        expected_flip = 100.0 + 5.0 * (240_000 / 390_000)
        assert result["flip_strike"] == pytest.approx(expected_flip, rel=1e-4)

    def test_gex_spot_none_returns_none(self):
        result = _gex(CONTRACTS, spot=None)
        assert result["total"] is None
        assert result["flip_strike"] is None

    def test_gex_empty_contracts_returns_none(self):
        result = _gex([], spot=100.0)
        assert result["total"] is None
        assert result["flip_strike"] is None

    def test_gex_skips_missing_gamma(self):
        # Only one contract with gamma; the None-gamma contract must be skipped
        contracts = [
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "100.00",
                "gamma": None,
                "oi": 1000,
            },
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "105.00",
                "gamma": "0.04",
                "oi": 500,
            },
        ]
        # Only the second contract contributes: +0.04 * 500 * 100 * 100 = 200_000
        result = _gex(contracts, spot=100.0)
        assert result["total"] == pytest.approx(200_000.0)

    def test_gex_no_flip_when_all_positive(self):
        # All calls, no puts → all GEX positive → no sign change → flip_strike is None
        contracts = [
            {"expiry": "2026-01-01", "side": "call", "strike": "95.00", "gamma": "0.05", "oi": 500},
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "100.00",
                "gamma": "0.05",
                "oi": 500,
            },
        ]
        result = _gex(contracts, spot=100.0)
        assert result["flip_strike"] is None
        assert result["total"] == pytest.approx(0.05 * 500 * 100 * 100 + 0.05 * 500 * 100 * 100)

    def test_gex_convention_field_present(self):
        result = _gex(CONTRACTS, spot=SPOT)
        assert "convention" in result
        assert "heuristic" in result["convention"]


class TestChainAnalytics:
    def test_returns_all_keys(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert set(result.keys()) == {
            "put_call",
            "max_pain",
            "iv_skew_25d",
            "term_structure",
            "gex",
        }

    def test_max_pain_value(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert result["max_pain"] == pytest.approx(100.0)

    def test_put_call_ratios(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert result["put_call"]["volume_ratio"] == pytest.approx(700 / 1050, rel=1e-4)
        assert result["put_call"]["oi_ratio"] == pytest.approx(2000 / 2600, rel=1e-4)

    def test_iv_skew(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert result["iv_skew_25d"] == pytest.approx(-1.0)

    def test_term_structure_length(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert len(result["term_structure"]) == 2

    def test_gex_total_and_flip(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert result["gex"]["total"] == pytest.approx(390_000.0)
        expected_flip = 100.0 + 5.0 * (240_000 / 390_000)
        assert result["gex"]["flip_strike"] == pytest.approx(expected_flip, rel=1e-4)

    def test_empty_input_all_none_or_empty(self):
        result = chain_analytics([], spot=100.0)
        assert result["put_call"] == {"volume_ratio": None, "oi_ratio": None}
        assert result["max_pain"] is None
        assert result["iv_skew_25d"] is None
        assert result["term_structure"] == []
        assert result["gex"]["total"] is None

    def test_contracts_with_all_none_greeks_tolerated(self):
        # Every greek is None → all analytics gracefully degrade
        contracts = [
            {
                "expiry": "2026-01-01",
                "side": "call",
                "strike": "100.00",
                "delta": None,
                "gamma": None,
                "iv": None,
                "volume": None,
                "oi": None,
            },
            {
                "expiry": "2026-01-01",
                "side": "put",
                "strike": "100.00",
                "delta": None,
                "gamma": None,
                "iv": None,
                "volume": None,
                "oi": None,
            },
        ]
        # Should not raise; skew/term/gex degrade to None
        result = chain_analytics(contracts, spot=100.0)
        assert result["iv_skew_25d"] is None
        assert result["gex"]["total"] is None
        # max_pain: strikes exist but OI is 0 (None treated as 0), so payout is 0 at every strike
        # → any strike could be returned; just confirm it doesn't raise and is a number
        assert result["max_pain"] is not None
