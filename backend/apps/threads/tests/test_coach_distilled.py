from __future__ import annotations

import pytest

from apps.thesis.models import Lesson
from apps.threads.coach import _distilled_lessons_block


@pytest.mark.django_db
def test_matches_by_sector_without_open_thesis():
    from apps.market.models import CompanyFundamentals

    CompanyFundamentals.objects.create(ticker="NVDA", sector="Technology")
    Lesson.objects.create(
        text="Tech lesson", tags={"directions": [], "sectors": ["Technology"]}, support_n=2
    )
    assert "Tech lesson" in _distilled_lessons_block("NVDA")
