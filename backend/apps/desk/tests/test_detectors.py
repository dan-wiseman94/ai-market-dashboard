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


def test_breadth_divergence_flags_uptrend_with_narrow_breadth():
    RegimeReading.objects.create(
        composite="Neutral-Transitional", axes={"trend": "Uptrend", "breadth": "Narrow"}
    )
    cands = D.detect_breadth_divergence()
    assert cands and cands[0]["anomaly_type"] == "breadth_divergence"
    assert cands[0]["ticker"] == ""  # book-wide
    assert cands[0]["evidence"] == {"trend": "Uptrend", "breadth": "Narrow"}


def test_breadth_divergence_no_flag_when_breadth_confirms():
    RegimeReading.objects.create(composite="Risk-On", axes={"trend": "Uptrend", "breadth": "Broad"})
    assert D.detect_breadth_divergence() == []


def test_earnings_proximity_flags_imminent_covered_name():
    from apps.market.models import MarketEvent

    MarketEvent.objects.create(
        source="seed",
        external_id="nvda-q1",
        kind="earnings",
        ticker="NVDA",
        title="NVDA earnings",
        event_time=timezone.now() + timezone.timedelta(days=1),
    )
    cands = D.detect_earnings_proximity(["NVDA", "AMD"])
    assert len(cands) == 1
    assert cands[0]["anomaly_type"] == "earnings_soon"
    assert cands[0]["ticker"] == "NVDA"
    assert cands[0]["evidence"]["days_until"] == 1


def test_earnings_proximity_ignores_far_out_earnings():
    from apps.market.models import MarketEvent

    MarketEvent.objects.create(
        source="seed",
        external_id="nvda-q2",
        kind="earnings",
        ticker="NVDA",
        title="NVDA earnings",
        event_time=timezone.now() + timezone.timedelta(days=30),
    )
    assert D.detect_earnings_proximity(["NVDA"]) == []


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
