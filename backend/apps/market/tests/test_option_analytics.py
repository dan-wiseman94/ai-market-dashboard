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

    def test_max_pain_skips_missing_strike(self):
        # Contract with no strike should be skipped, not cause a crash
        contracts = [
            {"expiry": "2026-01-01", "side": "call", "strike": None, "oi": 999},
            {"expiry": "2026-01-01", "side": "put", "strike": "100.00", "oi": 200},
        ]
        # Only strike 100 is valid; it's the only candidate, so it wins
        result = _max_pain(contracts)
        assert result == pytest.approx(100.0)


class TestIvSkew25d:
    def test_skew_nearest_expiry(self):
        # Nearest expiry "2026-01-01":
        #   call closest to |delta|=0.25 → call 105 (delta=0.25, iv=22.0)
        #   put  closest to |delta|=0.25 → put   95 (delta=-0.25, iv=21.0)
        # skew = IV(25d put) - IV(25d call) = 21.0 - 22.0 = -1.0
        result = _iv_skew_25d(CONTRACTS)
        assert result == pytest.approx(-1.0)

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

    def test_term_structure_spot_none_returns_none_atm_ivs(self):
        result = _term_structure(CONTRACTS, spot=None)
        assert len(result) == 2
        assert all(r["atm_iv"] is None for r in result)


class TestGex:
    def test_gex_spot_none_returns_none(self):
        result = _gex(CONTRACTS, spot=None)
        assert result["total"] is None
        assert result["flip_strike"] is None

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

    def test_gex_reports_top_strikes(self):
        contracts = [
            {"side": "call", "strike": 100, "gamma": "0.05", "oi": "1000"},
            {"side": "put", "strike": 95, "gamma": "0.04", "oi": "2000"},
            {"side": "call", "strike": 105, "gamma": "0.01", "oi": "100"},
        ]
        out = _gex(contracts, spot=100.0)
        strikes = [r["strike"] for r in out["by_strike"]]
        assert strikes == sorted(strikes)  # ascending for the render
        assert {r["strike"] for r in out["by_strike"]} == {95.0, 100.0, 105.0}
        assert out["by_strike"][0]["gex"] < 0  # 95 put wall is negative

    def test_gex_degrade_returns_carry_empty_by_strike(self):
        assert _gex([], spot=None)["by_strike"] == []
        assert _gex([], spot=100.0)["by_strike"] == []


class TestChainAnalytics:
    def test_put_call_ratios(self):
        result = chain_analytics(CONTRACTS, spot=SPOT)
        assert result["put_call"]["volume_ratio"] == pytest.approx(700 / 1050, rel=1e-4)
        assert result["put_call"]["oi_ratio"] == pytest.approx(2000 / 2600, rel=1e-4)

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


# ---------------------------------------------------------------------------
# flatten_expiries / put_call_from_expiries — the chain-payload-shaped
# entry points consumed by apps.snapshots.services.flowlite.
# ---------------------------------------------------------------------------
