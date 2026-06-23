"""Options-implied 1σ expected move from a chain payload (deterministic + defensive)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from apps.market.services import expected_move as em

TODAY = date(2026, 1, 1)


def _payload(expiries: dict[str, float], *, underlying: str | None = "100.00") -> dict:
    """expiries = {iso_date: atm_iv_decimal}; single ATM strike at the spot."""
    return {
        "underlying_last": underlying,
        "expiries": {
            d: {
                "calls": [
                    {"strike": "100", "iv": str(iv), "delta": "0.50", "bid": "1", "ask": "1.1"}
                ],
                "puts": [
                    {"strike": "100", "iv": str(iv), "delta": "-0.50", "bid": "1", "ask": "1.1"}
                ],
            }
            for d, iv in expiries.items()
        },
    }


@pytest.mark.parametrize(
    "iv,h,expected",
    [
        (0.20, 30, 0.20 * math.sqrt(30 / 365)),
        (0.40, 7, 0.40 * math.sqrt(7 / 365)),
        (0.30, 90, 0.30 * math.sqrt(90 / 365)),
    ],
)
def test_one_sigma_pct(iv, h, expected):
    assert em.one_sigma_pct(iv, h) == pytest.approx(expected)


def test_one_sigma_pct_normalizes_percent_iv():
    # Schwab gives the volatility field as a percent (25.0 == 0.25 decimal).
    assert em.one_sigma_pct(25.0, 30) == pytest.approx(em.one_sigma_pct(0.25, 30))


@pytest.mark.parametrize("bad", [None, 0, -0.1])
def test_one_sigma_pct_bad_iv_is_none(bad):
    assert em.one_sigma_pct(bad, 30) is None


def test_one_sigma_pct_nonpositive_horizon_is_none():
    assert em.one_sigma_pct(0.2, 0) is None


def test_for_horizon_picks_nearest_expiry():
    # expiries 10 and 40 days out; horizon 30 → 40d is nearer (|40-30|=10 < |10-30|=20).
    p = _payload(
        {
            (TODAY + timedelta(days=10)).isoformat(): 0.30,
            (TODAY + timedelta(days=40)).isoformat(): 0.20,
        }
    )
    assert em.for_horizon(p, 30, today=TODAY) == pytest.approx(em.one_sigma_pct(0.20, 30))


def test_for_horizon_ignores_expired():
    p = _payload(
        {
            (TODAY - timedelta(days=5)).isoformat(): 0.90,  # already expired — ignored
            (TODAY + timedelta(days=35)).isoformat(): 0.25,
        }
    )
    assert em.for_horizon(p, 30, today=TODAY) == pytest.approx(em.one_sigma_pct(0.25, 30))


def test_term_structure_emits_each_horizon():
    p = _payload(
        {
            (TODAY + timedelta(days=7)).isoformat(): 0.20,
            (TODAY + timedelta(days=30)).isoformat(): 0.25,
            (TODAY + timedelta(days=90)).isoformat(): 0.30,
        }
    )
    ts = em.term_structure(p, today=TODAY)
    assert [r["horizon_days"] for r in ts] == [7, 30, 90]
    row30 = next(r for r in ts if r["horizon_days"] == 30)
    assert row30["move_pct"] == pytest.approx(round(em.one_sigma_pct(0.25, 30), 4))
    assert row30["move_abs"] == pytest.approx(round(100.0 * em.one_sigma_pct(0.25, 30), 2))


@pytest.mark.parametrize(
    "payload", [{}, {"expiries": {}}, {"underlying_last": "100", "expiries": {}}]
)
def test_no_chain_is_empty_and_none(payload):
    assert em.term_structure(payload, today=TODAY) == []
    assert em.for_horizon(payload, 30, today=TODAY) is None
