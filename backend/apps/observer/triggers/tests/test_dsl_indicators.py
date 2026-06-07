import pytest
from django.core.exceptions import ValidationError

from apps.observer.triggers.dsl import validate_condition
from apps.observer.triggers.evaluator import leaf_key


def ok(node):
    validate_condition(node)


def bad(node):
    with pytest.raises(ValidationError):
        validate_condition(node)


def test_rsi_leaf_valid_with_params():
    ok(
        {
            "metric": "rsi",
            "ticker": "NVDA",
            "window": "1d",
            "op": "<",
            "value": 30,
            "params": {"period": 14},
        }
    )


def test_rsi_requires_window():
    bad({"metric": "rsi", "ticker": "NVDA", "op": "<", "value": 30, "params": {"period": 14}})


def test_sma_spread_fast_lt_slow():
    bad(
        {
            "metric": "sma_spread_pct",
            "ticker": "NVDA",
            "window": "1d",
            "op": "crosses_above",
            "value": 0,
            "params": {"fast": 200, "slow": 50},
        }
    )


def test_daily_only_rejects_window():
    bad({"metric": "gap_pct", "ticker": "NVDA", "window": "1d", "op": ">", "value": 0.03})


def test_daily_only_ok_without_window():
    ok({"metric": "gap_pct", "ticker": "NVDA", "op": ">", "value": 0.03})


def test_unknown_param_rejected():
    bad(
        {
            "metric": "rsi",
            "ticker": "NVDA",
            "window": "1d",
            "op": "<",
            "value": 30,
            "params": {"perdiod": 14},
        }
    )


def test_leaf_keys():
    assert (
        leaf_key({"metric": "rsi", "ticker": "NVDA", "window": "1d", "params": {"period": 14}})
        == "rsi:NVDA:1d:14"
    )
    assert leaf_key({"metric": "gap_pct", "ticker": "NVDA"}) == "gap_pct:NVDA"
    assert (
        leaf_key(
            {
                "metric": "sma_spread_pct",
                "ticker": "NVDA",
                "window": "1d",
                "params": {"fast": 50, "slow": 200},
            }
        )
        == "sma_spread_pct:NVDA:1d:50:200"
    )
