"""AIPrediction extraction from a structured observation."""

from __future__ import annotations

import pytest

from apps.observer.models import AIPrediction
from apps.observer.predictions.services.extract import extract_from_observation
from apps.observer.schemas import ObservationReport, Signal
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


# ---------------------------------------------------------------------------
# Dedup invariant: a partial UNIQUE constraint (status="open") on
# (ticker, horizon_days, profile) is the real guard behind the racy check-then-act;
# extract catches the IntegrityError as the race-loser no-op.
# ---------------------------------------------------------------------------


def _open_kwargs(profile, **over):
    from django.utils import timezone

    base = dict(
        ticker="NVDA",
        horizon_days=7,
        confidence=0.5,
        provider="claude",
        model="m",
        profile=profile,
        predicted_at=timezone.now(),
        resolve_at=timezone.now(),
        status="open",
    )
    base.update(over)
    return base


@pytest.mark.django_db
def test_second_open_prediction_violates_unique_constraint():
    from django.db import IntegrityError, transaction

    p = _profile()
    AIPrediction.objects.create(direction="bullish", **_open_kwargs(p))
    with pytest.raises(IntegrityError), transaction.atomic():
        AIPrediction.objects.create(direction="bearish", **_open_kwargs(p))


@pytest.mark.django_db
def test_null_profile_still_collides_on_open_constraint():
    """nulls_distinct=False — two open rows with a NULL profile must still collide."""
    from django.db import IntegrityError, transaction

    AIPrediction.objects.create(direction="bullish", **_open_kwargs(None))
    with pytest.raises(IntegrityError), transaction.atomic():
        AIPrediction.objects.create(direction="bearish", **_open_kwargs(None))


@pytest.mark.django_db
def test_constraint_allows_second_when_first_is_not_open():
    p = _profile()
    AIPrediction.objects.create(direction="bullish", **_open_kwargs(p, status="resolved"))
    # No IntegrityError — the partial index only covers status="open".
    AIPrediction.objects.create(direction="bearish", **_open_kwargs(p))
    assert AIPrediction.objects.count() == 2


@pytest.mark.django_db
def test_extract_race_loser_returns_the_concurrent_open():
    """When a concurrent fire opens a prediction between our dedup .first() and our
    create(), the DB constraint rejects ours (IntegrityError) — extract must swallow
    it and return the already-open winner, not crash the fire."""
    from unittest.mock import patch

    from apps.observer.predictions.services import extract as extract_mod

    p = _profile()
    snap = _snap(p, "NVDA")
    winner = AIPrediction.objects.create(direction="bearish", **_open_kwargs(p, confidence=0.4))

    real_filter = AIPrediction.objects.filter
    state = {"n": 0}

    class _MissQS:
        def first(self):
            return None

    def fake_filter(*args, **kwargs):
        # Make ONLY the first dedup lookup miss the winner (the check-then-act race
        # window); the except-branch re-fetch uses the real queryset.
        if kwargs.get("status") == "open" and state["n"] == 0:
            state["n"] += 1
            return _MissQS()
        return real_filter(*args, **kwargs)

    with patch.object(AIPrediction.objects, "filter", side_effect=fake_filter):
        result = extract_mod.extract_from_observation(
            _report(direction="bullish"),
            snapshot=snap,
            message=None,
            provider="claude",
            model="m",
            profile=p,
        )

    assert result is not None
    assert result.id == winner.id
    assert AIPrediction.objects.filter(status="open").count() == 1


# ---------------------------------------------------------------------------
# Expected-move freeze: the options-implied 1σ move for the prediction's
# horizon is captured at decision time from the snapshot's own chain section.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_extract_freezes_expected_move_from_chain():
    from datetime import date, timedelta

    from apps.market.services import expected_move as em
    from apps.snapshots.models import SnapshotSection

    profile = _profile()
    snap = _snap(profile, ticker="NVDA")
    future = (date.today() + timedelta(days=10)).isoformat()
    chain_payload = {
        "underlying_last": "100.00",
        "expiries": {
            future: {
                "calls": [
                    {"strike": "100", "bid": "1", "ask": "1.1", "delta": "0.5", "iv": "0.20"}
                ],
                "puts": [
                    {"strike": "100", "bid": "1", "ask": "1.1", "delta": "-0.5", "iv": "0.20"}
                ],
            }
        },
    }
    SnapshotSection.objects.create(
        snapshot=snap, kind="chain", status="done", payload=chain_payload
    )

    pred = _extract(_report(direction="bullish", horizon=7), snap, profile)
    assert pred is not None
    assert pred.expected_move_pct == pytest.approx(em.for_horizon(chain_payload, 7), rel=1e-3)


@pytest.mark.django_db
def test_extract_without_chain_freezes_none():
    profile = _profile()
    snap = _snap(profile, ticker="NVDA")  # no chain section
    pred = _extract(_report(), snap, profile)
    assert pred is not None
    assert pred.expected_move_pct is None
