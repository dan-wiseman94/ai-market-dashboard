from apps.triggers.evaluator import evaluate

METRICS = {"price:SPY": 551.0, "vix": 22.0, "price:QQQ": 480.0}


def test_all_group_true_when_all_leaves_match():
    node = {"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        {"metric": "vix", "op": ">", "value": 20},
    ]}
    matched, values = evaluate(node, METRICS)
    assert matched is True
    assert "price:SPY" in values and "vix" in values


def test_all_group_false_short_circuits():
    # Second leaf would read a missing key; we short-circuit on the first failing leaf.
    node = {"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
        {"metric": "price", "ticker": "NOPE", "op": ">", "value": 0},
    ]}
    matched, values = evaluate(node, METRICS)
    assert matched is False
    # Only the first leaf's key landed in values
    assert values == {"price:SPY": 551.0}


def test_any_group_true_on_first_match():
    node = {"any": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
        {"metric": "vix", "op": ">", "value": 100},
    ]}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_any_group_false_when_all_miss():
    node = {"any": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
        {"metric": "vix", "op": ">", "value": 100},
    ]}
    matched, _ = evaluate(node, METRICS)
    assert matched is False


def test_not_flips_leaf():
    node = {"not": {"metric": "vix", "op": ">", "value": 100}}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_not_flips_group():
    node = {"not": {"all": [
        {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
    ]}}
    matched, _ = evaluate(node, METRICS)
    assert matched is True


def test_empty_all_group_is_true():
    matched, values = evaluate({"all": []}, METRICS)
    assert matched is True
    assert values == {}


def test_empty_any_group_is_false():
    matched, values = evaluate({"any": []}, METRICS)
    assert matched is False
    assert values == {}


def test_nested_all_inside_any():
    node = {"any": [
        {"all": [
            {"metric": "price", "ticker": "SPY", "op": ">", "value": 600},
            {"metric": "vix", "op": ">", "value": 10},
        ]},
        {"metric": "price", "ticker": "QQQ", "op": ">", "value": 400},
    ]}
    matched, _ = evaluate(node, METRICS)
    assert matched is True   # second branch matches
