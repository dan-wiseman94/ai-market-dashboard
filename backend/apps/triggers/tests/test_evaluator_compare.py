import pytest

from apps.triggers.evaluator import evaluate

METRICS = {
    "price:SPY": 551.2,
    "price:QQQ": 480.0,
    "vix": 22.5,
    "position_pl": -350.0,
    "position_pl_pct": -0.025,
}


@pytest.mark.parametrize(
    "op,value,expected",
    [
        (">", 550, True),
        (">=", 551.2, True),
        ("<", 600, True),
        ("<=", 551.2, True),
        ("==", 551.2, True),
        (">", 551.2, False),
        (">=", 551.3, False),
        ("<", 551.2, False),
        ("<=", 551.19, False),
        ("==", 551.19, False),
    ],
)
def test_price_comparison_ops(op, value, expected):
    node = {"metric": "price", "ticker": "SPY", "op": op, "value": value}
    matched, values = evaluate(node, METRICS)
    assert matched is expected
    assert values == {"price:SPY": 551.2}


def test_vix_leaf_reads_bare_key():
    node = {"metric": "vix", "op": ">", "value": 20}
    matched, values = evaluate(node, METRICS)
    assert matched is True
    assert values == {"vix": 22.5}


def test_position_pl_reads_bare_key():
    node = {"metric": "position_pl", "op": "<", "value": -300}
    matched, values = evaluate(node, METRICS)
    assert matched is True
    assert values == {"position_pl": -350.0}


def test_position_pl_pct_reads_bare_key():
    node = {"metric": "position_pl_pct", "op": "<=", "value": -0.02}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_pct_change_reads_keyed_with_window():
    m = {"pct_change:SPY:5m": 0.014}
    node = {"metric": "pct_change", "ticker": "SPY", "op": ">=", "value": 0.01, "window": "5m"}
    matched, values = evaluate(node, m)
    assert matched is True
    assert values == {"pct_change:SPY:5m": 0.014}


def test_missing_metric_returns_false():
    node = {"metric": "price", "ticker": "TSLA", "op": ">", "value": 100}
    matched, values = evaluate(node, METRICS)
    assert matched is False
    assert values == {"price:TSLA": None}


def test_none_metric_returns_false():
    m = {"price:SPY": None}
    node = {"metric": "price", "ticker": "SPY", "op": ">", "value": 0}
    matched, values = evaluate(node, m)
    assert matched is False
    assert values == {"price:SPY": None}
