import pytest

from apps.strategy.desk.services.universe import build_universe
from apps.strategy.models import CoverageNote
from apps.thesis.models import Thesis

pytestmark = pytest.mark.django_db


def test_universe_unions_sources():
    Thesis.objects.create(
        title="t", ticker="nvda", direction="bullish", conviction=3, status="open"
    )
    CoverageNote.objects.create(ticker="AMD", stance="bull", conviction=3)
    uni = build_universe()
    assert "NVDA" in uni and "AMD" in uni  # upper-cased, de-duped
