import pytest

from apps.observer.triggers.evaluator import evaluate

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
