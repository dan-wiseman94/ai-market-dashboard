import pytest

from apps.book.services import analytics as A

pytestmark = pytest.mark.django_db

EXPOSURES = [
    {
        "ticker": "NVDA",
        "net_signed": 7.0,
        "abs_exposure": 7.0,
        "dollar": None,
        "sources": ["thesis"],
    },
    {
        "ticker": "AMD",
        "net_signed": 4.0,
        "abs_exposure": 4.0,
        "dollar": None,
        "sources": ["thesis"],
    },
    {
        "ticker": "TLT",
        "net_signed": -2.0,
        "abs_exposure": 2.0,
        "dollar": None,
        "sources": ["thesis"],
    },
]


def test_concentration_shares_and_net():
    c = A.concentration(EXPOSURES)
    assert c["total_abs"] == 13.0
    assert round(c["top_n_share"], 2) == 1.0
    assert c["net_long"] == 11.0
    assert c["net_short"] == -2.0
    assert 0 < c["hhi"] <= 1.0


def test_concentration_empty():
    c = A.concentration([])
    assert c["total_abs"] == 0 and c["top_n_share"] == 0.0


def test_near_invalidation_flags_close_stops():
    from django.utils import timezone

    from apps.market.models import OHLCBar
    from apps.thesis.models import Thesis

    Thesis.objects.create(
        title="x",
        ticker="NVDA",
        direction="bullish",
        conviction=4,
        status="open",
        invalidation_price=100,
    )
    OHLCBar.objects.create(
        ticker="NVDA",
        timeframe="1d",
        open=103,
        high=103,
        low=103,
        close=103,
        volume=1,
        ts=timezone.now(),
    )  # 3% above stop -> near
    near = A.near_invalidation()
    assert any(r["ticker"] == "NVDA" for r in near)


def test_regime_fit_misaligned(monkeypatch):
    class _R:
        composite = "Risk-Off"

    monkeypatch.setattr(A, "current_regime", lambda: _R())
    fit = A.regime_fit(EXPOSURES)  # net long 9 vs short 2 -> net long, into Risk-Off
    assert fit["regime"] == "Risk-Off"
    assert fit["alignment"] == "misaligned"


def test_regime_fit_no_regime(monkeypatch):
    monkeypatch.setattr(A, "current_regime", lambda: None)
    assert A.regime_fit(EXPOSURES)["alignment"] == "unknown"
