import pytest
from django.core.exceptions import ValidationError

from apps.triggers.dsl import validate_condition


def test_validate_price_leaf_ok():
    validate_condition({"metric": "price", "ticker": "SPY", "op": ">", "value": 550})


def test_validate_pct_change_requires_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "pct_change", "ticker": "SPY", "op": ">=", "value": 0.01})
    assert "window" in str(exc.value)


def test_validate_price_rejects_window():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 550, "window": "5m"}
        )
    assert "window" in str(exc.value)


def test_validate_all_group_ok():
    validate_condition(
        {
            "all": [
                {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
                {"metric": "vix", "op": ">", "value": 20},
            ]
        }
    )


def test_validate_any_group_ok():
    validate_condition(
        {
            "any": [
                {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
                {"metric": "price", "ticker": "QQQ", "op": ">", "value": 480},
            ]
        }
    )


def test_validate_not_wraps_one_node():
    validate_condition({"not": {"metric": "vix", "op": ">", "value": 30}})


def test_validate_not_rejects_multiple():
    with pytest.raises(ValidationError):
        validate_condition(
            {
                "not": [
                    {"metric": "vix", "op": ">", "value": 30},
                    {"metric": "vix", "op": "<", "value": 10},
                ]
            }
        )


def test_validate_unknown_metric():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "foo", "ticker": "SPY", "op": ">", "value": 1})
    assert "metric" in str(exc.value)


def test_validate_unknown_op():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "price", "ticker": "SPY", "op": "??", "value": 1})
    assert "op" in str(exc.value)


def test_validate_price_requires_ticker():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "price", "op": ">", "value": 1})
    assert "ticker" in str(exc.value)


def test_validate_vix_ticker_optional():
    validate_condition({"metric": "vix", "op": ">", "value": 20})
    validate_condition({"metric": "vix", "ticker": "$VIX", "op": ">", "value": 20})


def test_validate_window_must_be_valid():
    with pytest.raises(ValidationError):
        validate_condition(
            {"metric": "pct_change", "ticker": "SPY", "op": ">", "value": 0.01, "window": "7m"}
        )


def test_validate_value_must_be_number():
    with pytest.raises(ValidationError):
        validate_condition({"metric": "price", "ticker": "SPY", "op": ">", "value": "550"})


def test_validate_error_path_reports_location():
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "all": [
                    {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
                    {"metric": "bad", "ticker": "SPY", "op": ">", "value": 1},
                ]
            }
        )
    assert ".all[1]" in str(exc.value)


def test_validate_empty_group_ok():
    validate_condition({"all": []})
    validate_condition({"any": []})


def test_validate_rejects_typo_leaf_keys():
    """Typos like 'windoww' / 'tikcer' would silently evaluate wrong; reject early."""
    with pytest.raises(ValidationError) as exc:
        validate_condition(
            {
                "metric": "price",
                "ticker": "SPY",
                "op": ">",
                "value": 1,
                "windoww": "5m",
            }
        )
    assert "windoww" in str(exc.value)


def test_validate_ticker_must_be_string():
    with pytest.raises(ValidationError) as exc:
        validate_condition({"metric": "price", "ticker": ["SPY"], "op": ">", "value": 1})
    assert "ticker" in str(exc.value)


def test_validate_root_must_be_dict():
    with pytest.raises(ValidationError) as exc:
        validate_condition([{"metric": "price", "ticker": "SPY", "op": ">", "value": 1}])
    assert "<root>" in str(exc.value)
