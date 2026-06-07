import pytest

from apps.strategy.warroom.services.subject import subject_context
from apps.thesis.models import Thesis

pytestmark = pytest.mark.django_db


def test_free_prompt():
    label, ctx = subject_context(free_prompt="Is NVDA a buy into earnings?")
    assert "NVDA" in ctx and label


def test_thesis_subject():
    t = Thesis.objects.create(
        title="NVDA breakout",
        ticker="NVDA",
        direction="bullish",
        conviction=4,
        status="open",
        rationale="AI capex",
    )
    label, ctx = subject_context(thesis=t)
    assert "NVDA" in ctx and "bullish" in ctx
    assert "NVDA" in label
