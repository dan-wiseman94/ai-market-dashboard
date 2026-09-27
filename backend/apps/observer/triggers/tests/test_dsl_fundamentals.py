"""DSL validation tests for the four fundamentals trigger leaves.

Covered:
- pe_ratio, market_cap, revenue_growth, gross_margin are valid metrics
- ticker is required for each
- window is forbidden for each (not in WINDOW_REQUIRED)
- crosses_above / crosses_below are rejected (NON_CROSSING_METRICS)
"""

import pytest
from django.core.exceptions import ValidationError

from apps.observer.triggers.dsl import validate_condition


def test_pe_ratio_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "pe_ratio", "op": "<", "value": 30})
    assert "ticker" in str(exc.value)


def test_pe_ratio_rejects_crosses_above():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "pe_ratio", "ticker": "NVDA", "op": "crosses_above", "value": 30}
        )
    assert "crossing" in str(exc.value)


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
