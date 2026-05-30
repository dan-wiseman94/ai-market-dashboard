"""DSL validation tests for the four fundamentals trigger leaves.

Covered:
- pe_ratio, market_cap, revenue_growth, gross_margin are valid metrics
- ticker is required for each
- window is forbidden for each (not in WINDOW_REQUIRED)
- crosses_above / crosses_below are rejected (NON_CROSSING_METRICS)
"""

import pytest
from django.core.exceptions import ValidationError

from apps.triggers.dsl import validate_condition

# ── pe_ratio ──────────────────────────────────────────────────────────────────


def test_pe_ratio_valid_leaf():
    validate_condition({"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30})


def test_pe_ratio_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "pe_ratio", "op": "<", "value": 30})
    assert "ticker" in str(exc.value)


def test_pe_ratio_rejects_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30, "window": "1d"}
        )
    assert "window" in str(exc.value)


def test_pe_ratio_rejects_crosses_above():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "pe_ratio", "ticker": "NVDA", "op": "crosses_above", "value": 30}
        )
    assert "crossing" in str(exc.value)


def test_pe_ratio_rejects_crosses_below():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "pe_ratio", "ticker": "NVDA", "op": "crosses_below", "value": 30}
        )
    assert "crossing" in str(exc.value)


# ── market_cap ────────────────────────────────────────────────────────────────


def test_market_cap_valid_leaf():
    validate_condition({"metric": "market_cap", "ticker": "NVDA", "op": ">=", "value": 1_000_000})


def test_market_cap_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "market_cap", "op": ">=", "value": 1_000_000})
    assert "ticker" in str(exc.value)


def test_market_cap_rejects_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "metric": "market_cap",
                "ticker": "NVDA",
                "op": ">=",
                "value": 1_000_000,
                "window": "1d",
            }
        )
    assert "window" in str(exc.value)


def test_market_cap_rejects_crossing_op():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "market_cap", "ticker": "NVDA", "op": "crosses_above", "value": 1_000_000}
        )
    assert "crossing" in str(exc.value)


# ── revenue_growth ────────────────────────────────────────────────────────────


def test_revenue_growth_valid_leaf():
    validate_condition({"metric": "revenue_growth", "ticker": "NVDA", "op": ">", "value": 0.1})


def test_revenue_growth_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "revenue_growth", "op": ">", "value": 0.1})
    assert "ticker" in str(exc.value)


def test_revenue_growth_rejects_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "metric": "revenue_growth",
                "ticker": "NVDA",
                "op": ">",
                "value": 0.1,
                "window": "1d",
            }
        )
    assert "window" in str(exc.value)


def test_revenue_growth_rejects_crossing_op():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "revenue_growth", "ticker": "NVDA", "op": "crosses_below", "value": 0.0}
        )
    assert "crossing" in str(exc.value)


# ── gross_margin ──────────────────────────────────────────────────────────────


def test_gross_margin_valid_leaf():
    validate_condition({"metric": "gross_margin", "ticker": "NVDA", "op": ">", "value": 60.0})


def test_gross_margin_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "gross_margin", "op": ">", "value": 60.0})
    assert "ticker" in str(exc.value)


def test_gross_margin_rejects_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "gross_margin", "ticker": "NVDA", "op": ">", "value": 60.0, "window": "1d"}
        )
    assert "window" in str(exc.value)


def test_gross_margin_rejects_crossing_op():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "gross_margin", "ticker": "NVDA", "op": "crosses_above", "value": 60.0}
        )
    assert "crossing" in str(exc.value)


# ── combined condition (the motivating use case) ──────────────────────────────


def test_cheap_into_earnings_condition_is_valid():
    """Canonical compound: low PE and near earnings — both must pass validation."""
    validate_condition(
        {
            "all": [
                {"metric": "pe_ratio", "ticker": "NVDA", "op": "<", "value": 30},
                {"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 3},
            ]
        }
    )
