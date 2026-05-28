from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.analytics.services.calibration import _prob_for_conviction, calibration
from apps.profiles.models import TradingProfile
from apps.thesis.models import PostMortem, Thesis
from apps.threads.models import AIRun, Message, Thread

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
WIN = (NOW - timedelta(days=90), NOW + timedelta(days=1))


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="p", style="s")


def _thesis(conviction: int, direction: str = "bullish", thread=None) -> Thesis:
    return Thesis.objects.create(
        title="t",
        ticker="NVDA",
        direction=direction,
        conviction=conviction,
        status="closed_win",
        thread=thread,
    )


def _pm(
    thesis: Thesis, *, horizon: int, verdict: str, fwd: float | None, completed: datetime = NOW
) -> PostMortem:
    return PostMortem.objects.create(
        thesis=thesis,
        horizon_days=horizon,
        due_at=completed,
        status="done",
        verdict=verdict,
        forward_return_pct=fwd,
        completed_at=completed,
    )


def test_prob_for_conviction_maps_1_to_0_5_and_5_to_0_9():
    assert _prob_for_conviction(1) == 0.5
    assert _prob_for_conviction(3) == 0.7
    assert _prob_for_conviction(5) == 0.9


@pytest.mark.django_db
def test_thesis_buckets_and_overall_hitrate(profile):
    _pm(_thesis(5), horizon=30, verdict="correct", fwd=8.0)
    _pm(_thesis(5), horizon=30, verdict="incorrect", fwd=-3.0)
    _pm(_thesis(2), horizon=30, verdict="correct", fwd=2.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    th = out["thesis"]
    b5 = next(b for b in th["buckets"] if b["conviction"] == 5)
    assert b5["n"] == 2 and b5["correct"] == 1 and b5["incorrect"] == 1
    assert b5["hit_rate"] == 0.5
    assert th["overall"]["scored"] == 3
    assert th["overall"]["hit_rate"] == round(2 / 3, 4)


@pytest.mark.django_db
def test_brier_known_value(profile):
    # conviction 5 (p=0.9) correct -> (0.9-1)^2=0.01 ; conviction 1 (p=0.5) incorrect -> 0.25
    _pm(_thesis(5), horizon=30, verdict="correct", fwd=5.0)
    _pm(_thesis(1), horizon=30, verdict="incorrect", fwd=-5.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["thesis"]["brier"] == round((0.01 + 0.25) / 2, 4)


@pytest.mark.django_db
def test_horizon_selects_one_pm_per_thesis(profile):
    t = _thesis(4)
    _pm(t, horizon=7, verdict="incorrect", fwd=-1.0)
    _pm(t, horizon=30, verdict="correct", fwd=6.0)
    _pm(t, horizon=90, verdict="correct", fwd=9.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["thesis"]["overall"]["scored"] == 1
    assert out["thesis"]["overall"]["correct"] == 1


@pytest.mark.django_db
def test_mixed_inconclusive_counted_but_excluded_from_hitrate(profile):
    _pm(_thesis(3), horizon=30, verdict="mixed", fwd=0.5)
    _pm(_thesis(3), horizon=30, verdict="inconclusive", fwd=0.2)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    ov = out["thesis"]["overall"]
    assert ov["mixed"] == 1 and ov["inconclusive"] == 1
    assert ov["hit_rate"] is None  # no correct/incorrect → undefined


@pytest.mark.django_db
def test_provider_attribution_via_source_thread(profile):
    thread = Thread.objects.create(kind="consult", profile=profile)
    msg = Message.objects.create(
        thread=thread, role="assistant", content={"text": ""}, status="done"
    )
    AIRun.objects.create(
        message=msg,
        provider="claude",
        model="claude-opus-4-7",
        cost_usd=Decimal("0.1"),
        latency_ms=1000,
        status="done",
    )
    _pm(_thesis(5, thread=thread), horizon=30, verdict="correct", fwd=7.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["attributable"] == 1
    row = next(r for r in out["provider"] if r["provider"] == "claude")
    assert row["n"] == 1 and row["correct"] == 1 and row["hit_rate"] == 1.0


@pytest.mark.django_db
def test_empty_input_returns_zeros_no_crash(profile):
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["thesis"]["overall"]["scored"] == 0
    assert out["thesis"]["brier"] is None
    assert out["thesis"]["overall"]["hit_rate"] is None
    assert out["provider"] == [] and out["attributable"] == 0
    assert len(out["thesis"]["buckets"]) == 5
