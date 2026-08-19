"""Scorecard drill-down: calibration buckets -> underlying theses.

Mirrors the fixtures in test_calibration.py. The drill-down returns the same
PostMortem ⋈ Thesis population that builds the calibration buckets, filtered to
one bucket (conviction / direction / verdict), so counts reconcile with the
aggregate scorecard.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from apps.analytics.services.calibration import calibration, calibration_drilldown
from apps.profiles.models import TradingProfile
from apps.thesis.models import PostMortem, Thesis

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
WIN = (NOW - timedelta(days=90), NOW + timedelta(days=1))


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="p", style="s")


@pytest.fixture
def api():
    return APIClient()


def _thesis(conviction: int, *, direction: str = "bullish", title: str = "t") -> Thesis:
    return Thesis.objects.create(
        title=title, ticker="NVDA", direction=direction, conviction=conviction, status="closed_win"
    )


def _pm(thesis: Thesis, *, horizon: int, verdict: str, fwd: float | None) -> PostMortem:
    return PostMortem.objects.create(
        thesis=thesis,
        horizon_days=horizon,
        due_at=NOW,
        status="done",
        verdict=verdict,
        forward_return_pct=fwd,
        completed_at=NOW,
    )


@pytest.mark.django_db
def test_drilldown_filters_by_conviction(profile):
    a = _thesis(5, title="five-correct")
    _pm(a, horizon=30, verdict="correct", fwd=8.0)
    b = _thesis(5, title="five-incorrect")
    _pm(b, horizon=30, verdict="incorrect", fwd=-3.0)
    c = _thesis(2, title="two")
    _pm(c, horizon=30, verdict="correct", fwd=2.0)

    out = calibration_drilldown(start=WIN[0], end=WIN[1], horizon=30, conviction=5)
    assert out["count"] == 2
    assert {r["thesis_id"] for r in out["rows"]} == {a.id, b.id}

    row = next(r for r in out["rows"] if r["thesis_id"] == a.id)
    for key in (
        "thesis_id",
        "title",
        "ticker",
        "direction",
        "conviction",
        "verdict",
        "forward_return_pct",
        "horizon_days",
        "completed_at",
        "thread_id",
    ):
        assert key in row
    assert row["title"] == "five-correct"
    assert isinstance(row["forward_return_pct"], float)
    assert row["forward_return_pct"] == 8.0


@pytest.mark.django_db
def test_drilldown_filters_by_verdict_and_direction(profile):
    bull_ok = _thesis(4, direction="bullish")
    _pm(bull_ok, horizon=30, verdict="correct", fwd=5.0)
    bull_bad = _thesis(4, direction="bullish")
    _pm(bull_bad, horizon=30, verdict="incorrect", fwd=-5.0)
    bear_ok = _thesis(4, direction="bearish")
    _pm(bear_ok, horizon=30, verdict="correct", fwd=-5.0)

    by_verdict = calibration_drilldown(start=WIN[0], end=WIN[1], horizon=30, verdict="incorrect")
    assert {r["thesis_id"] for r in by_verdict["rows"]} == {bull_bad.id}

    by_dir = calibration_drilldown(start=WIN[0], end=WIN[1], horizon=30, direction="bearish")
    assert {r["thesis_id"] for r in by_dir["rows"]} == {bear_ok.id}

    combined = calibration_drilldown(
        start=WIN[0], end=WIN[1], horizon=30, conviction=4, verdict="correct"
    )
    assert {r["thesis_id"] for r in combined["rows"]} == {bull_ok.id, bear_ok.id}


@pytest.mark.django_db
def test_drilldown_count_reconciles_with_bucket_n(profile):
    """drilldown(conviction=C).count must equal the calibration bucket[C].n."""
    _pm(_thesis(3), horizon=30, verdict="correct", fwd=2.0)
    _pm(_thesis(3), horizon=30, verdict="mixed", fwd=0.5)
    _pm(_thesis(3), horizon=30, verdict="incorrect", fwd=-2.0)
    # An inconclusive (null fwd) row is excluded from BOTH the buckets and the drill-down.
    _pm(_thesis(3), horizon=30, verdict="inconclusive", fwd=None)

    cal = calibration(start=WIN[0], end=WIN[1], horizon=30)
    b3 = next(b for b in cal["thesis"]["buckets"] if b["conviction"] == 3)
    dd = calibration_drilldown(start=WIN[0], end=WIN[1], horizon=30, conviction=3)
    assert dd["count"] == b3["n"] == 3


@pytest.mark.django_db
def test_drilldown_respects_horizon_and_window(profile):
    in_h = _thesis(3)
    _pm(in_h, horizon=30, verdict="correct", fwd=1.0)
    other_h = _thesis(3)
    _pm(other_h, horizon=7, verdict="correct", fwd=1.0)
    out = calibration_drilldown(start=WIN[0], end=WIN[1], horizon=30)
    assert {r["thesis_id"] for r in out["rows"]} == {in_h.id}


@pytest.mark.django_db
def test_drilldown_endpoint_shape(api, profile):
    t = _thesis(5)
    _pm(t, horizon=30, verdict="correct", fwd=4.0)
    r = api.get("/api/analytics/calibration/drilldown/?conviction=5&horizon=30")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["filters"]["conviction"] == 5
    assert "start" in body and "end" in body
    assert body["rows"][0]["thesis_id"] == t.id


@pytest.mark.django_db
def test_drilldown_endpoint_no_filters_returns_all_in_window(api, profile):
    _pm(_thesis(1), horizon=30, verdict="correct", fwd=1.0)
    _pm(_thesis(4), horizon=30, verdict="incorrect", fwd=-1.0)
    body = api.get("/api/analytics/calibration/drilldown/?horizon=30").json()
    assert body["count"] == 2
    assert body["filters"] == {"conviction": None, "direction": None, "verdict": None}
