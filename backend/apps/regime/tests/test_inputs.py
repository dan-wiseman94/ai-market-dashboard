import pytest
from django.utils import timezone

from apps.market.models import OHLCBar
from apps.regime.services import inputs as I

pytestmark = pytest.mark.django_db


def _seed_daily(ticker, closes):
    base = timezone.now()
    for i, px in enumerate(closes):
        OHLCBar.objects.create(
            ticker=ticker, timeframe="1d", open=px, high=px, low=px, close=px,
            volume=1, ts=base - timezone.timedelta(days=len(closes) - i),
        )


def test_gather_inputs_shape_and_degradation(monkeypatch):
    monkeypatch.setattr(I, "fetch_market_context", lambda: {"vix_last": 22.0, "breadth": {"$ADVN": 1500, "$DECN": 900}})
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})
    out = I.gather_inputs()
    assert out["vix_last"] == 22.0
    assert out["breadth"] == {"$ADVN": 1500, "$DECN": 900}
    assert out["spx_ma_spread"] is None  # no $SPX bars
    assert out["t10y2y"] is None


def test_gather_inputs_computes_spx_trend(monkeypatch):
    monkeypatch.setattr(I, "fetch_market_context", lambda: {"vix_last": 15.0, "breadth": {}})
    monkeypatch.setattr(I, "fetch_macro", lambda ids: {})
    _seed_daily("$SPX", [100.0 + i for i in range(220)])  # rising series
    out = I.gather_inputs()
    assert out["spx_ma_spread"] is not None
    assert out["spx_dist_50"] is not None


def test_vix_percentile_needs_enough_history():
    assert I._vix_percentile(20.0, [18.0, 19.0]) is None  # < 30 bars
    pct = I._vix_percentile(20.0, [float(x) for x in range(40)])  # 20 of 40 <= 20
    assert pct is not None and 0.0 <= pct <= 1.0
