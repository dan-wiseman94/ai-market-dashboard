from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.analytics.services.calibration import track_record_for_ticker
from apps.thesis.models import PostMortem, Thesis

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _thesis(status: str, *, direction="bullish", conviction=4) -> Thesis:
    return Thesis.objects.create(
        title="t", ticker="NVDA", direction=direction, conviction=conviction, status=status
    )


def _pm(thesis: Thesis, verdict: str) -> PostMortem:
    return PostMortem.objects.create(
        thesis=thesis,
        horizon_days=30,
        due_at=NOW,
        status="done",
        verdict=verdict,
        forward_return_pct=1.0,
        completed_at=NOW,
    )


@pytest.mark.django_db
def test_returns_none_below_min_n_and_no_slice():
    _thesis("closed_win")
    _thesis("closed_loss")  # only 2 closed, < min_n=3, no direction/conviction slice
    assert track_record_for_ticker("NVDA") is None


@pytest.mark.django_db
def test_ticker_summary_counts_and_hit_rate():
    for st in ("closed_win", "closed_loss", "closed_loss", "invalidated"):
        _thesis(st)
    tr = track_record_for_ticker("NVDA")
    assert tr["closed_n"] == 4
    assert tr["counts"] == {"win": 1, "loss": 2, "scratch": 0, "invalidated": 1}
    assert tr["hit_rate"] == round(1 / 3, 4)  # win / (win+loss)


@pytest.mark.django_db
def test_direction_conviction_slice_from_postmortems():
    # 4 bullish/conv-4 closed theses; PM verdicts: 1 correct, 3 incorrect
    verdicts = ["correct", "incorrect", "incorrect", "incorrect"]
    for v in verdicts:
        _pm(_thesis("closed_win"), v)
    tr = track_record_for_ticker("NVDA", direction="bullish", conviction=4)
    assert tr["slice"] == {
        "direction": "bullish",
        "conviction": 4,
        "correct": 1,
        "n": 4,
        "hit_rate": 0.25,
    }


@pytest.mark.django_db
def test_empty_ticker_returns_none():
    assert track_record_for_ticker("") is None
