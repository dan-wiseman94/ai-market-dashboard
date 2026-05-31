"""AIPrediction extraction from a structured observation (M13 F1)."""

from __future__ import annotations

import pytest

from apps.observer.schemas import ObservationReport, Signal
from apps.predictions.models import AIPrediction
from apps.predictions.services.extract import extract_from_observation
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


def _profile() -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s")


def _snap(profile, ticker="NVDA") -> Snapshot:
    return Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["quotes"],
        source="observer",
        primary_ticker=ticker,
    )


def _report(direction="bullish", horizon=7, confidence=0.7, ticker="NVDA") -> ObservationReport:
    return ObservationReport(
        headline="NVDA breaking out",
        bias="bullish",
        summary="momentum building",
        signals=[
            Signal(
                ticker=ticker,
                bias="bullish",
                thesis="x",
                invalidation="below 100",
                confidence=confidence,
            )
        ],
        next_check_in="tomorrow",
        predicted_direction=direction,
        predicted_horizon_days=horizon,
        predicted_confidence=confidence,
    )


def _extract(report, snap, profile):
    return extract_from_observation(
        report,
        snapshot=snap,
        message=None,
        provider="claude",
        model="claude-opus-4-8",
        profile=profile,
    )


@pytest.mark.django_db
class TestExtract:
    def test_creates_prediction_from_directional_call(self):
        p = _profile()
        pred = _extract(_report(), _snap(p), p)
        assert pred is not None
        assert pred.ticker == "NVDA"
        assert pred.direction == "bullish"
        assert pred.horizon_days == 7
        assert pred.confidence == pytest.approx(0.7)
        assert pred.status == "open"
        assert pred.invalidation_note == "below 100"
        assert pred.provider == "claude"
        assert pred.resolve_at > pred.predicted_at

    def test_no_directional_call_returns_none(self):
        p = _profile()
        r = _report()
        r.predicted_direction = None
        assert _extract(r, _snap(p), p) is None
        assert AIPrediction.objects.count() == 0

    def test_confidence_falls_back_to_signal_mean(self):
        p = _profile()
        r = _report(confidence=0.6)
        r.predicted_confidence = None  # the per-signal 0.6 should be used
        pred = _extract(r, _snap(p), p)
        assert pred.confidence == pytest.approx(0.6)

    def test_no_confidence_anywhere_returns_none(self):
        p = _profile()
        r = ObservationReport(
            headline="h",
            bias="neutral",
            summary="s",
            signals=[],
            next_check_in="t",
            predicted_direction="bullish",
            predicted_horizon_days=7,
        )
        assert _extract(r, _snap(p), p) is None

    def test_default_horizon_when_unset(self):
        p = _profile()
        r = _report()
        r.predicted_horizon_days = None
        pred = _extract(r, _snap(p), p)
        assert pred.horizon_days == 7  # DEFAULT_HORIZON_DAYS

    def test_dedup_same_direction_is_noop(self):
        p = _profile()
        snap = _snap(p)
        a = _extract(_report(direction="bullish"), snap, p)
        b = _extract(_report(direction="bullish"), snap, p)
        assert a.id == b.id  # the open call stands, frozen
        assert AIPrediction.objects.filter(status="open").count() == 1

    def test_direction_flip_invalidates_old_and_creates_new(self):
        p = _profile()
        snap = _snap(p)
        a = _extract(_report(direction="bullish"), snap, p)
        b = _extract(_report(direction="bearish"), snap, p)
        a.refresh_from_db()
        assert a.status == "invalidated"
        assert a.invalidated_at is not None
        assert b.id != a.id
        assert b.direction == "bearish"
        assert AIPrediction.objects.filter(status="open").count() == 1
