from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from apps.thesis.models import Lesson, PostMortem, Thesis
from apps.thesis.services.lessons_distill import distill_lessons

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _pm(ticker: str, direction: str, lessons: list[str], verdict: str = "incorrect") -> PostMortem:
    th = Thesis.objects.create(
        title="t", ticker=ticker, direction=direction, conviction=3, status="closed_loss"
    )
    return PostMortem.objects.create(
        thesis=th,
        horizon_days=30,
        due_at=NOW,
        status="done",
        verdict=verdict,
        report={"lessons": lessons},
        completed_at=NOW,
    )


# embed() is imported function-locally in distill — patch it at the source module.
def _embed(vectors):
    return patch("apps.recall.embeddings.embed", return_value=vectors)


@pytest.mark.django_db
def test_clusters_similar_lessons_into_one():
    _pm("AAA", "bearish", ["Too bullish into earnings"])
    _pm("BBB", "bearish", ["Too bullish into earnings"])
    with _embed([[1.0, 0.0], [1.0, 0.0]]):  # identical vectors -> cosine 1.0 -> merge
        res = distill_lessons()
    assert res["processed"] == 2
    assert Lesson.objects.count() == 1
    lesson = Lesson.objects.get()
    assert lesson.support_n == 2
    assert lesson.tags["directions"] == ["bearish"]


@pytest.mark.django_db
def test_separates_dissimilar_lessons():
    _pm("AAA", "bearish", ["Too bullish into earnings"])
    _pm("BBB", "bullish", ["Ignored the macro tape"])
    with _embed([[1.0, 0.0], [0.0, 1.0]]):  # orthogonal -> cosine 0 -> separate
        res = distill_lessons()
    assert res["created"] == 2
    assert Lesson.objects.count() == 2


@pytest.mark.django_db
def test_idempotent_skips_already_distilled():
    _pm("AAA", "bearish", ["Too bullish into earnings"])
    with _embed([[1.0, 0.0]]):
        distill_lessons()
        res2 = distill_lessons()  # PM now linked -> nothing new
    assert res2["processed"] == 0
    assert Lesson.objects.count() == 1


@pytest.mark.django_db
def test_skips_when_embeddings_unavailable():
    _pm("AAA", "bearish", ["x"])
    with _embed(None):
        res = distill_lessons()
    assert res.get("skipped") == "no_embeddings"
    assert Lesson.objects.count() == 0


@pytest.mark.django_db
def test_merges_sector_tags_from_fundamentals():
    from apps.market.models import CompanyFundamentals

    CompanyFundamentals.objects.create(ticker="AAA", sector="Technology")
    CompanyFundamentals.objects.create(ticker="BBB", sector="Healthcare")
    _pm("AAA", "bearish", ["Too bullish into earnings"])
    _pm("BBB", "bearish", ["Too bullish into earnings"])
    with _embed([[1.0, 0.0], [1.0, 0.0]]):
        distill_lessons()
    lesson = Lesson.objects.get()
    assert lesson.tags["sectors"] == ["Healthcare", "Technology"]
