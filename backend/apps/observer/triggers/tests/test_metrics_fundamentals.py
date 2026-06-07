"""Metrics resolution tests for the four fundamentals trigger leaves.

Covered:
- leaf_key shape for each fundamental metric
- build_snapshot resolves pe_ratio and market_cap from fetch_fundamentals
- build_snapshot resolves revenue_growth and gross_margin
- fetch_fundamentals returns {} (cold/no key) → leaf is ABSENT from snapshot, no crash
- fetch_fundamentals returns None value → leaf is ABSENT, not 0
- one fetch_fundamentals call per distinct ticker (batching)
- evaluate() returns True when snapshot value satisfies the condition
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.observer.triggers.evaluator import evaluate, leaf_key
from apps.observer.triggers.metrics import build_snapshot

PATCH_TARGET = "apps.observer.triggers.metrics.fetch_fundamentals"

_FULL_FUND = {
    "ticker": "NVDA",
    "pe": 25.0,
    "market_cap": 3.4e12,
    "rev_growth_yoy": 0.22,
    "gross_margin": 74.5,
}


def _trigger(condition):
    return SimpleNamespace(condition=condition)


# ── leaf_key ──────────────────────────────────────────────────────────────────


def test_leaf_key_pe_ratio():
    assert (
        leaf_key({"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30})
        == "pe_ratio:NVDA"
    )


def test_leaf_key_market_cap():
    assert (
        leaf_key({"metric": "market_cap", "ticker": "NVDA", "op": ">=", "value": 1e12})
        == "market_cap:NVDA"
    )


def test_leaf_key_revenue_growth():
    assert (
        leaf_key({"metric": "revenue_growth", "ticker": "NVDA", "op": ">", "value": 0.1})
        == "revenue_growth:NVDA"
    )


def test_leaf_key_gross_margin():
    assert (
        leaf_key({"metric": "gross_margin", "ticker": "NVDA", "op": ">", "value": 60.0})
        == "gross_margin:NVDA"
    )


# ── resolved values ───────────────────────────────────────────────────────────


def test_build_snapshot_resolves_pe_ratio():
    cond = {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30}
    with patch(PATCH_TARGET, return_value=_FULL_FUND) as mock_fetch:
        snap = build_snapshot([_trigger(cond)])
    assert snap["pe_ratio:NVDA"] == 25.0
    mock_fetch.assert_called_once_with("NVDA")


def test_build_snapshot_resolves_market_cap():
    cond = {"metric": "market_cap", "ticker": "NVDA", "op": ">=", "value": 1e12}
    with patch(PATCH_TARGET, return_value=_FULL_FUND):
        snap = build_snapshot([_trigger(cond)])
    assert snap["market_cap:NVDA"] == 3.4e12


def test_build_snapshot_resolves_revenue_growth():
    cond = {"metric": "revenue_growth", "ticker": "NVDA", "op": ">", "value": 0.1}
    with patch(PATCH_TARGET, return_value=_FULL_FUND):
        snap = build_snapshot([_trigger(cond)])
    assert snap["revenue_growth:NVDA"] == pytest.approx(0.22)


def test_build_snapshot_resolves_gross_margin():
    cond = {"metric": "gross_margin", "ticker": "NVDA", "op": ">", "value": 60.0}
    with patch(PATCH_TARGET, return_value=_FULL_FUND):
        snap = build_snapshot([_trigger(cond)])
    assert snap["gross_margin:NVDA"] == pytest.approx(74.5)


# ── evaluate integration ──────────────────────────────────────────────────────


def test_evaluate_pe_ratio_matches():
    cond = {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30}
    with patch(PATCH_TARGET, return_value=_FULL_FUND):
        snap = build_snapshot([_trigger(cond)])
    matched, values = evaluate(cond, snap)
    assert matched is True
    assert values["pe_ratio:NVDA"] == 25.0


def test_evaluate_pe_ratio_no_match():
    cond = {"metric": "pe_ratio", "ticker": "NVDA", "op": ">", "value": 100}
    with patch(PATCH_TARGET, return_value=_FULL_FUND):
        snap = build_snapshot([_trigger(cond)])
    matched, _ = evaluate(cond, snap)
    assert matched is False


# ── missing/cold fundamentals → leaf ABSENT, no crash ────────────────────────


def test_missing_fundamentals_leaf_absent_from_snapshot():
    """fetch_fundamentals returns {} (no API key / cold) → key not in snapshot."""
    cond = {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30}
    with patch(PATCH_TARGET, return_value={}):
        snap = build_snapshot([_trigger(cond)])
    assert "pe_ratio:NVDA" not in snap


def test_missing_fundamentals_evaluates_false():
    """Absent metric evaluates as no-match (not a crash, not a spurious fire)."""
    cond = {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30}
    with patch(PATCH_TARGET, return_value={}):
        snap = build_snapshot([_trigger(cond)])
    matched, _ = evaluate(cond, snap)
    assert matched is False


def test_none_fundamental_value_leaf_absent():
    """If the dict has the key but the value is None, the leaf must also be absent."""
    fund_with_none = {**_FULL_FUND, "pe": None}
    cond = {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30}
    with patch(PATCH_TARGET, return_value=fund_with_none):
        snap = build_snapshot([_trigger(cond)])
    assert "pe_ratio:NVDA" not in snap


# ── per-ticker batching (one fetch per distinct ticker) ───────────────────────


def test_fundamentals_fetched_once_per_ticker():
    """Two pe_ratio leaves for the same ticker → only one fetch_fundamentals call."""
    cond = {
        "all": [
            {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30},
            {"metric": "gross_margin", "ticker": "NVDA", "op": ">", "value": 60.0},
        ]
    }
    with patch(PATCH_TARGET, return_value=_FULL_FUND) as mock_fetch:
        build_snapshot([_trigger(cond)])
    mock_fetch.assert_called_once_with("NVDA")


def test_fundamentals_fetched_once_per_distinct_ticker():
    """Two different tickers → two fetch_fundamentals calls (one each)."""
    aapl_fund = {**_FULL_FUND, "ticker": "AAPL", "pe": 28.0, "gross_margin": 43.0}
    cond_nvda = {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30}
    cond_aapl = {"metric": "pe_ratio", "ticker": "AAPL", "op": "<", "value": 30}

    def _side_effect(ticker):
        return _FULL_FUND if ticker == "NVDA" else aapl_fund

    with patch(PATCH_TARGET, side_effect=_side_effect) as mock_fetch:
        snap = build_snapshot([_trigger(cond_nvda), _trigger(cond_aapl)])

    assert mock_fetch.call_count == 2
    assert snap["pe_ratio:NVDA"] == 25.0
    assert snap["pe_ratio:AAPL"] == 28.0


# ── compound condition: cheap into earnings ───────────────────────────────────


@pytest.mark.django_db
def test_cheap_into_earnings_snapshot_keys_present():
    """Both leaves populate independent keys — compound condition can evaluate."""
    cond = {
        "all": [
            {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30},
            {"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 3},
        ]
    }
    # patch fetch_fundamentals; days_to_earnings path uses the DB (absent → None → no-match)
    with patch(PATCH_TARGET, return_value=_FULL_FUND):
        snap = build_snapshot([_trigger(cond)])

    assert snap["pe_ratio:NVDA"] == 25.0
    # days_to_earnings may be absent (no DB row) — that's fine; we just check pe was resolved
    assert "pe_ratio:NVDA" in snap
