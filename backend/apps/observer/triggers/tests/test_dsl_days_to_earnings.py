import pytest
from django.core.exceptions import ValidationError

from apps.observer.triggers.dsl import validate_condition


def test_days_to_earnings_valid():
    validate_condition({"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 2})


def test_days_to_earnings_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "days_to_earnings", "op": "<=", "value": 2})
    assert "ticker" in str(exc.value)


def test_days_to_earnings_rejects_crossing_op():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "days_to_earnings", "ticker": "NVDA", "op": "crosses_below", "value": 2}
        )
    assert "crossing" in str(exc.value)


def test_days_to_earnings_rejects_window():
    with pytest.raises(ValidationError):
        validate_condition(
            {"metric": "days_to_earnings", "ticker": "NVDA", "op": "<=", "value": 2, "window": "1d"}
        )
