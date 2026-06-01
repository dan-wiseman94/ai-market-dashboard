from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.analytics.services.trader_calibration import trader_calibration
from apps.thesis.models import DecisionJournalEntry, PostMortem, Thesis
from apps.threads.models import Thread

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _thesis_pm(
    ticker: str, verdict: str, *, direction="bullish", conviction=3, horizon=30
) -> Thesis:
    th = Thesis.objects.create(
        title="t", ticker=ticker, direction=direction, conviction=conviction, status="closed_loss"
    )
    PostMortem.objects.create(
        thesis=th,
        horizon_days=horizon,
        due_at=NOW,
        status="done",
        verdict=verdict,
        forward_return_pct=1.0,
        completed_at=NOW,
    )
    return th


def _journal(th: Thesis, decision: str) -> None:
    thread = Thread.objects.create(kind="consult", title="x")
    DecisionJournalEntry.objects.create(thread=thread, thesis=th, decision=decision)


@pytest.mark.django_db
def test_decision_outcomes_hit_rate():
    for i, v in enumerate(["correct", "correct", "correct", "incorrect"]):
        _journal(_thesis_pm(f"P{i}", v), "passed")
    res = trader_calibration(horizon_days=30)["decision_outcomes"]
    assert res["status"] == "ok"
    passed = next(b for b in res["buckets"] if b["decision"] == "passed")
    assert passed["n"] == 4
    assert passed["correct"] == 3
    assert passed["hit_rate"] == 0.75


@pytest.mark.django_db
def test_decision_below_min_n_insufficient():
    for i, v in enumerate(["correct", "incorrect"]):  # 2 < 4
        _journal(_thesis_pm(f"Q{i}", v), "acted")
    assert (
        trader_calibration(horizon_days=30)["decision_outcomes"]["status"] == "insufficient_history"
    )


@pytest.mark.django_db
def test_conviction_inverted_verdict():
    for i in range(4):
        _thesis_pm(f"H{i}", "incorrect", conviction=5)  # "sure things" all wrong
    for i in range(4):
        _thesis_pm(f"L{i}", "correct", conviction=1)  # hedged maybes all right
    rel = trader_calibration(horizon_days=30)["conviction_reliability"]
    assert rel["verdict"] == "inverted"
    assert rel["status"] == "ok"


@pytest.mark.django_db
def test_conviction_aligned_verdict():
    for i in range(4):
        _thesis_pm(f"H{i}", "correct", conviction=5)
    for i in range(4):
        _thesis_pm(f"L{i}", "incorrect", conviction=1)
    assert trader_calibration(horizon_days=30)["conviction_reliability"]["verdict"] == "aligned"


@pytest.mark.django_db
def test_endpoint_returns_structure():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/analytics/trader-calibration/?horizon=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["horizon_days"] == 30
    assert "decision_outcomes" in data
    assert "conviction_reliability" in data
