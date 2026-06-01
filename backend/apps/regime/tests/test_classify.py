import pytest

from apps.regime.services import classify as c


@pytest.mark.parametrize(
    "vix,expected",
    [(10.0, "Low"), (16.0, "Normal"), (24.0, "Elevated"), (35.0, "Stress"), (None, "Unknown")],
)
def test_classify_volatility(vix, expected):
    assert c.classify_volatility(vix) == expected


@pytest.mark.parametrize(
    "ma_spread,dist50,expected",
    [
        (5.0, 3.0, "Uptrend"),
        (-4.0, -2.0, "Downtrend"),
        (5.0, -1.0, "Range"),
        (None, None, "Unknown"),
    ],
)
def test_classify_trend(ma_spread, dist50, expected):
    assert c.classify_trend(ma_spread, dist50) == expected


@pytest.mark.parametrize(
    "breadth,expected",
    [
        ({"$ADVN": 2000, "$DECN": 800}, "Broad"),
        ({"$ADVN": 800, "$DECN": 2000}, "Narrow"),
        ({"$ADVN": 1000, "$DECN": 1000}, "Mixed"),
        ({"$ADVN": 1500, "$DECN": 1000, "$TRIN": 2.5}, "Deteriorating"),
        ({}, "Unknown"),
    ],
)
def test_classify_breadth(breadth, expected):
    assert c.classify_breadth(breadth) == expected


@pytest.mark.parametrize(
    "rets,expected",
    [
        ({"XLK": 3.0, "XLY": 2.0, "XLC": 2.0, "XLU": 0.0, "XLP": 0.0, "XLV": 0.0}, "Offensive"),
        ({"XLK": -2.0, "XLY": -2.0, "XLC": -2.0, "XLU": 1.0, "XLP": 1.0, "XLV": 1.0}, "Defensive"),
        ({"XLK": 1.0, "XLY": 1.0, "XLC": 1.0, "XLU": 0.8, "XLP": 0.8, "XLV": 0.8}, "Mixed"),
        ({"XLK": 1.0}, "Unknown"),
    ],
)
def test_classify_leadership(rets, expected):
    assert c.classify_leadership(rets) == expected


@pytest.mark.parametrize(
    "t10y2y,tnx_change,expected",
    [
        (-0.3, 0.0, "Inverted"),
        (0.5, 0.05, "Tightening"),
        (0.5, -0.05, "Easing"),
        (0.5, 0.0, "Steepening"),
        (None, None, "Unknown"),
    ],
)
def test_classify_rates(t10y2y, tnx_change, expected):
    assert c.classify_rates(t10y2y, tnx_change) == expected


def test_fold_composite_risk_on():
    axes = {
        "volatility": "Low",
        "trend": "Uptrend",
        "breadth": "Broad",
        "leadership": "Offensive",
        "rates": "Easing",
    }
    assert c.fold_composite(axes) == "Risk-On"


def test_fold_composite_risk_off():
    axes = {
        "volatility": "Elevated",
        "trend": "Downtrend",
        "breadth": "Narrow",
        "leadership": "Defensive",
        "rates": "Inverted",
    }
    assert c.fold_composite(axes) == "Risk-Off"


def test_fold_composite_stress_short_circuit():
    axes = {
        "volatility": "Stress",
        "trend": "Uptrend",
        "breadth": "Broad",
        "leadership": "Offensive",
        "rates": "Easing",
    }
    assert c.fold_composite(axes) == "Stress"


def test_fold_composite_neutral_when_mixed_or_unknown():
    axes = {
        "volatility": "Normal",
        "trend": "Range",
        "breadth": "Unknown",
        "leadership": "Unknown",
        "rates": "Unknown",
    }
    assert c.fold_composite(axes) == "Neutral-Transitional"


def test_build_drivers_skips_unknown():
    axes = {
        "volatility": "Elevated",
        "trend": "Downtrend",
        "breadth": "Unknown",
        "leadership": "Unknown",
        "rates": "Unknown",
    }
    inp = {"vix_last": 24.0, "vix_percentile": 0.82}
    drivers = c.build_drivers(axes, inp)
    assert any("VIX 24" in d for d in drivers)
    assert all("Unknown" not in d for d in drivers)
