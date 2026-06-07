from __future__ import annotations

import pytest

from apps.thesis.models import Lesson, Thesis
from apps.threads.coach import _distilled_lessons_block


@pytest.mark.django_db
def test_surfaces_matching_lesson_by_direction():
    Thesis.objects.create(
        title="t", ticker="NVDA", direction="bearish", conviction=3, status="open"
    )
    Lesson.objects.create(
        text="You anchor to round numbers",
        tags={"directions": ["bearish"], "sectors": []},
        support_n=3,
    )
    assert "anchor to round numbers" in _distilled_lessons_block("NVDA")


@pytest.mark.django_db
def test_empty_below_min_support():
    Thesis.objects.create(
        title="t", ticker="NVDA", direction="bearish", conviction=3, status="open"
    )
    Lesson.objects.create(text="x", tags={"directions": ["bearish"]}, support_n=1)
    assert _distilled_lessons_block("NVDA") == ""


@pytest.mark.django_db
def test_empty_when_no_thesis_and_no_sector():
    Lesson.objects.create(text="x", tags={"directions": ["bearish"]}, support_n=3)
    assert _distilled_lessons_block("NVDA") == ""


@pytest.mark.django_db
def test_matches_by_sector_without_open_thesis():
    from apps.market.models import CompanyFundamentals

    CompanyFundamentals.objects.create(ticker="NVDA", sector="Technology")
    Lesson.objects.create(
        text="Tech lesson", tags={"directions": [], "sectors": ["Technology"]}, support_n=2
    )
    assert "Tech lesson" in _distilled_lessons_block("NVDA")
