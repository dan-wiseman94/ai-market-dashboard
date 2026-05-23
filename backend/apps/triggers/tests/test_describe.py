from apps.triggers.services.describe import describe


def test_describe_price_leaf():
    assert describe({"price:SPY": 551.23}) == "SPY=551.23"


def test_describe_pct_change():
    # Percentage with two decimals, leading +/-
    assert describe({"pct_change:SPY:5m": 0.0142}) == "SPY +1.42% / 5m"
    assert describe({"pct_change:NVDA:1h": -0.024}) == "NVDA -2.40% / 1h"


def test_describe_volume_z():
    assert describe({"volume_z:NVDA:5m": 3.2}) == "NVDA vol z=3.20 / 5m"


def test_describe_vix():
    assert describe({"vix": 22.5}) == "vix=22.50"


def test_describe_position_pl():
    assert describe({"position_pl": -312.4}) == "position_pl=-312.40"


def test_describe_position_pl_pct():
    assert describe({"position_pl_pct": -0.018}) == "position_pl -1.80%"


def test_describe_multiple_joined_with_comma():
    out = describe({"price:SPY": 551.2, "vix": 22.5})
    assert "SPY=551.20" in out
    assert "vix=22.50" in out
    assert "," in out


def test_describe_ignores_prior_keys():
    out = describe({"price:SPY": 551.2, "_prior:price:SPY": 549.0})
    assert out == "SPY=551.20"


def test_describe_ignores_none_values():
    out = describe({"price:SPY": None, "vix": 22.5})
    assert out == "vix=22.50"


def test_describe_empty():
    assert describe({}) == ""
