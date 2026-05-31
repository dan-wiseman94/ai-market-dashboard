"""Invalidation-price extraction (key-levels heuristic) + early-warning alerts (M13 F5)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.market.models import OHLCBar
from apps.observer.schemas import KeyLevel, ObservationReport, Signal
from apps.predictions.models import AIPrediction
from apps.predictions.services.extract import extract_from_observation
from apps.predictions.tasks import check_invalidations
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


def _profile():
    return TradingProfile.objects.create(name="p", style="s")


def _snap(profile, ticker="NVDA", last=100.0):
    snap = Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["quotes"],
        source="observer",
        primary_ticker=ticker,
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={ticker: {"last": last}}
    )
    return snap


def _report(direction="bullish", levels=None, ticker="NVDA"):
    return ObservationReport(
        headline="h",
        bias="bullish",
        summary="s",
        signals=[
            Signal(
                ticker=ticker,
                bias="bullish",
                thesis="x",
                invalidation="below support",
                confidence=0.7,
            )
        ],
        key_levels=levels or [],
        next_check_in="t",
        predicted_direction=direction,
        predicted_horizon_days=7,
        predicted_confidence=0.7,
    )


def _extract(report, snap, profile):
    return extract_from_observation(
        report, snapshot=snap, message=None, provider="claude", model="m", profile=profile
    )


@pytest.mark.django_db
class TestInvalidationPriceExtraction:
    def test_bullish_uses_nearest_support_below(self):
        p = _profile()
        levels = [
            KeyLevel(label="s1", price=90, kind="support"),
            KeyLevel(label="s2", price=80, kind="support"),
            KeyLevel(label="r", price=110, kind="resistance"),
        ]
        pred = _extract(_report("bullish", levels), _snap(p, last=100.0), p)
        assert float(pred.invalidation_price) == 90.0  # highest support below 100

    def test_bearish_uses_nearest_resistance_above(self):
        p = _profile()
        levels = [
            KeyLevel(label="r1", price=110, kind="resistance"),
            KeyLevel(label="r2", price=120, kind="resistance"),
        ]
        pred = _extract(_report("bearish", levels), _snap(p, last=100.0), p)
        assert float(pred.invalidation_price) == 110.0  # lowest resistance above 100

    def test_neutral_has_no_price(self):
        p = _profile()
        levels = [KeyLevel(label="s", price=90, kind="support")]
        pred = _extract(_report("neutral", levels), _snap(p), p)
        assert pred.invalidation_price is None

    def test_no_levels_no_price(self):
        p = _profile()
        pred = _extract(_report("bullish", []), _snap(p), p)
        assert pred.invalidation_price is None


def _open_pred(direction="bullish", inv=90.0, ticker="NVDA"):
    now = timezone.now()
    return AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=7,
        confidence=0.7,
        provider="claude",
        model="m",
        predicted_at=now - timedelta(days=1),
        resolve_at=now + timedelta(days=7),  # still before horizon
        status="open",
        invalidation_price=inv,
    )


def _bar(ticker, close):
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1h",
        ts=timezone.now(),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


@pytest.mark.django_db
class TestCheckInvalidations:
    def test_marks_and_notifies_on_breach(self):
        pred = _open_pred(direction="bullish", inv=90.0)
        _bar("NVDA", 85.0)  # 85 <= 90 -> breached
        with patch("apps.observer.services.notifications.notify") as mock_notify:
            out = check_invalidations()
        pred.refresh_from_db()
        assert pred.status == "invalidated"
        assert pred.invalidated_at is not None
        assert out["invalidated"] == 1
        mock_notify.assert_called_once()

    def test_no_breach_leaves_open(self):
        pred = _open_pred(direction="bullish", inv=90.0)
        _bar("NVDA", 95.0)  # 95 > 90 -> not breached
        check_invalidations()
        pred.refresh_from_db()
        assert pred.status == "open"

    def test_bearish_breach_on_break_above(self):
        pred = _open_pred(direction="bearish", inv=110.0)
        _bar("NVDA", 115.0)  # 115 >= 110 -> breached
        with patch("apps.observer.services.notifications.notify"):
            check_invalidations()
        pred.refresh_from_db()
        assert pred.status == "invalidated"

    def test_ignores_predictions_without_invalidation_price(self):
        _open_pred(inv=None)
        _bar("NVDA", 1.0)
        assert check_invalidations()["invalidated"] == 0
