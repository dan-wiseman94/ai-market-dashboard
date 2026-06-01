import pytest
from django.utils import timezone

from apps.book.models import BookSnapshot
from apps.desk.services import detectors as D
from apps.market.models import OHLCBar
from apps.regime.models import RegimeReading

pytestmark = pytest.mark.django_db


def test_price_detector_flags_big_move():
    base = timezone.now()
    OHLCBar.objects.create(
        ticker="NVDA",
        timeframe="1d",
        open=100,
        high=100,
        low=100,
        close=100,
        volume=1,
        ts=base - timezone.timedelta(days=1),
    )
    OHLCBar.objects.create(
        ticker="NVDA", timeframe="1d", open=100, high=110, low=100, close=110, volume=1, ts=base
    )
    cands = D.detect_price(["NVDA"])
    assert any(c["anomaly_type"] == "price_move" and c["ticker"] == "NVDA" for c in cands)


def test_regime_change_detector():
    RegimeReading.objects.create(composite="Risk-On", axes={})
    RegimeReading.objects.create(composite="Risk-Off", axes={})
    cands = D.detect_regime_change()
    assert cands and cands[0]["anomaly_type"] == "regime_change"


def test_regime_no_change_no_candidate():
    RegimeReading.objects.create(composite="Risk-On", axes={})
    RegimeReading.objects.create(composite="Risk-On", axes={})
    assert D.detect_regime_change() == []


def test_book_deterioration_detector():
    BookSnapshot.objects.create(
        as_of_date=timezone.now().date() - timezone.timedelta(days=1),
        concentration={"hhi": 0.2},
        regime_fit={"alignment": "aligned"},
    )
    BookSnapshot.objects.create(
        as_of_date=timezone.now().date(),
        concentration={"hhi": 0.5},
        regime_fit={"alignment": "misaligned"},
    )
    cands = D.detect_book()
    assert cands and cands[0]["anomaly_type"] == "book_deterioration"


def test_run_detectors_aggregates(monkeypatch):
    monkeypatch.setattr(
        D,
        "detect_price",
        lambda uni: [
            {"anomaly_type": "price_move", "ticker": "X", "severity": 5.0, "evidence": {}}
        ],
    )
    monkeypatch.setattr(D, "detect_options", lambda uni: [])
    monkeypatch.setattr(D, "detect_regime_change", lambda: [])
    monkeypatch.setattr(D, "detect_book", lambda: [])
    monkeypatch.setattr(D, "detect_coverage_stale", lambda uni: [])
    out = D.run_detectors(["X"])
    assert len(out) == 1 and out[0]["ticker"] == "X"
