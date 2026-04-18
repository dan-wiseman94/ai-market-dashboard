from apps.triggers.evaluator import evaluate


def test_crosses_above_fires_on_sign_change():
    metrics = {"price:SPY": 551.0, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, values = evaluate(node, metrics)
    assert matched is True
    assert values == {"price:SPY": 551.0, "_prior:price:SPY": 549.0}


def test_crosses_above_requires_prior_below_or_equal():
    metrics = {"price:SPY": 552.0, "_prior:price:SPY": 551.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_above_requires_current_strictly_above():
    metrics = {"price:SPY": 550.0, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_below_fires_on_sign_change():
    metrics = {"price:SPY": 549.5, "_prior:price:SPY": 550.5}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_below", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is True


def test_crosses_below_requires_prior_above_or_equal():
    metrics = {"price:SPY": 548.0, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_below", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_missing_prior_returns_false():
    metrics = {"price:SPY": 551.0, "_prior:price:SPY": None}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_missing_current_returns_false():
    metrics = {"price:SPY": None, "_prior:price:SPY": 549.0}
    node = {"metric": "price", "ticker": "SPY", "op": "crosses_above", "value": 550}
    matched, _ = evaluate(node, metrics)
    assert matched is False


def test_crosses_on_vix():
    metrics = {"vix": 30.5, "_prior:vix": 29.0}
    node = {"metric": "vix", "op": "crosses_above", "value": 30}
    matched, _ = evaluate(node, metrics)
    assert matched is True
