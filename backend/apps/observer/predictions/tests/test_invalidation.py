"""Invalidation-price extraction (key-levels heuristic) + early-warning alerts."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.observer.models import AIPrediction, Notification
from apps.observer.predictions.services.extract import extract_from_observation
from apps.observer.predictions.tasks import check_invalidations
from apps.observer.schemas import KeyLevel, ObservationReport, Signal
from apps.snapshots.models import Snapshot, SnapshotSection


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
    def test_bullish_uses_nearest_support_below(self, profile):
        levels = [
            KeyLevel(label="s1", price=90, kind="support"),
            KeyLevel(label="s2", price=80, kind="support"),
            KeyLevel(label="r", price=110, kind="resistance"),
        ]
        pred = _extract(_report("bullish", levels), _snap(profile, last=100.0), profile)
        assert float(pred.invalidation_price) == 90.0  # highest support below 100

    def test_bearish_uses_nearest_resistance_above(self, profile):
        levels = [
            KeyLevel(label="r1", price=110, kind="resistance"),
            KeyLevel(label="r2", price=120, kind="resistance"),
        ]
        pred = _extract(_report("bearish", levels), _snap(profile, last=100.0), profile)
        assert float(pred.invalidation_price) == 110.0  # lowest resistance above 100

    def test_neutral_has_no_price(self, profile):
        levels = [KeyLevel(label="s", price=90, kind="support")]
        pred = _extract(_report("neutral", levels), _snap(profile), profile)
        assert pred.invalidation_price is None

    def test_no_levels_no_price(self, profile):
        pred = _extract(_report("bullish", []), _snap(profile), profile)
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


@pytest.mark.django_db
class TestCheckInvalidations:
    def test_marks_and_notifies_on_breach(self, mk_bar):
        pred = _open_pred(direction="bullish", inv=90.0)
        mk_bar("NVDA", timezone.now(), 85.0)  # 85 <= 90 -> breached
        # No mock: exercise the REAL notify() against the DB so a varchar(16)
        # overflow (the kind literal exceeding max_length) surfaces as a failure
        # instead of being swallowed by _notify_invalidated's best-effort wrapper.
        out = check_invalidations()
        pred.refresh_from_db()
        assert pred.status == "invalidated"
        assert pred.invalidated_at is not None
        assert out["invalidated"] == 1
        n = Notification.objects.get(kind="pred_invalid")
        assert n.link == "/scorecard"
        assert "NVDA" in n.title

    def test_no_breach_leaves_open(self, mk_bar):
        pred = _open_pred(direction="bullish", inv=90.0)
        mk_bar("NVDA", timezone.now(), 95.0)  # 95 > 90 -> not breached
        check_invalidations()
        pred.refresh_from_db()
        assert pred.status == "open"

    def test_bearish_breach_on_break_above(self, mk_bar):
        pred = _open_pred(direction="bearish", inv=110.0)
        mk_bar("NVDA", timezone.now(), 115.0)  # 115 >= 110 -> breached
        with patch("apps.observer.services.notifications.notify"):
            check_invalidations()
        pred.refresh_from_db()
        assert pred.status == "invalidated"

    def test_ignores_predictions_without_invalidation_price(self, mk_bar):
        _open_pred(inv=None)
        mk_bar("NVDA", timezone.now(), 1.0)
        assert check_invalidations()["invalidated"] == 0
