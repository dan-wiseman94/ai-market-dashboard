from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.analytics.services.cohorts import cohort_base_rate
from apps.thesis.models import PostMortem, Thesis

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _decisive(ticker: str, direction: str, verdict: str) -> None:
    th = Thesis.objects.create(
        title="t", ticker=ticker, direction=direction, conviction=3, status="closed_loss"
    )
    PostMortem.objects.create(
        thesis=th,
        horizon_days=30,
        due_at=NOW,
        status="done",
        verdict=verdict,
        forward_return_pct=1.0,
        completed_at=NOW,
    )


@pytest.mark.django_db
def test_all_direction_cohort_hit_rate():
    for t, v in [
        ("AAA", "correct"),
        ("BBB", "correct"),
        ("CCC", "incorrect"),
        ("DDD", "incorrect"),
        ("EEE", "incorrect"),
    ]:
        _decisive(t, "bearish", v)
    assert cohort_base_rate(direction="bearish", ticker="ZZZ") == {
        "scope": "all",
        "n": 5,
        "correct": 2,
        "hit_rate": 0.4,
    }


@pytest.mark.django_db
def test_below_min_n_returns_none():
    for t, v in [("AAA", "correct"), ("BBB", "incorrect"), ("CCC", "incorrect")]:  # 3 < 4
        _decisive(t, "bearish", v)
    assert cohort_base_rate(direction="bearish", ticker="ZZZ") is None


@pytest.mark.django_db
def test_excludes_current_ticker():
    for _ in range(4):
        _decisive("NVDA", "bearish", "correct")  # excluded
    for t in ("AAA", "BBB", "CCC", "DDD"):
        _decisive(t, "bearish", "incorrect")
    res = cohort_base_rate(direction="bearish", ticker="NVDA")
    assert res["n"] == 4 and res["correct"] == 0


@pytest.mark.django_db
def test_only_decisive_and_same_direction_counted():
    for t in ("AAA", "BBB", "CCC", "DDD"):
        _decisive(t, "bearish", "incorrect")
    _decisive("EEE", "bullish", "correct")  # other direction
    th = Thesis.objects.create(
        title="t", ticker="FFF", direction="bearish", conviction=3, status="closed_loss"
    )
    PostMortem.objects.create(  # non-decisive verdict
        thesis=th, horizon_days=30, due_at=NOW, status="done", verdict="mixed", completed_at=NOW
    )
    res = cohort_base_rate(direction="bearish", ticker="ZZZ")
    assert res["n"] == 4  # only the 4 decisive bearish


@pytest.mark.django_db
def test_prefers_sector_cohort_when_enough():
    from apps.market.models import CompanyFundamentals

    for t in ("AAA", "BBB", "CCC", "DDD"):  # Technology cohort, all wrong
        CompanyFundamentals.objects.create(ticker=t, sector="Technology")
        _decisive(t, "bearish", "incorrect")
    for t in ("EEE", "FFF", "GGG", "HHH"):  # other sectors, all right
        _decisive(t, "bearish", "correct")
    CompanyFundamentals.objects.create(ticker="ZZZ", sector="Technology")

    res = cohort_base_rate(direction="bearish", ticker="ZZZ")
    assert res["scope"] == "Technology"
    assert res["n"] == 4 and res["correct"] == 0
