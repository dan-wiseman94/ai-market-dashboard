import pytest

from apps.book.services.exposures import build_exposures
from apps.coverage.models import CoverageNote
from apps.thesis.models import Thesis

pytestmark = pytest.mark.django_db


def test_union_aggregates_by_ticker_signed_by_conviction():
    Thesis.objects.create(
        title="t", ticker="NVDA", direction="bullish", conviction=4, status="open"
    )
    CoverageNote.objects.create(ticker="NVDA", stance="bull", conviction=3)
    Thesis.objects.create(title="s", ticker="TLT", direction="bearish", conviction=2, status="open")
    rows = {r["ticker"]: r for r in build_exposures()}
    assert rows["NVDA"]["net_signed"] == 7  # +4 thesis +3 coverage
    assert "thesis" in rows["NVDA"]["sources"] and "coverage" in rows["NVDA"]["sources"]
    assert rows["TLT"]["net_signed"] == -2
    assert build_exposures()[0]["ticker"] == "NVDA"  # sorted by abs exposure desc


def test_neutral_contributes_zero():
    Thesis.objects.create(
        title="n", ticker="AAPL", direction="neutral", conviction=5, status="open"
    )
    rows = {r["ticker"]: r for r in build_exposures()}
    assert rows["AAPL"]["net_signed"] == 0


def test_closed_theses_excluded():
    Thesis.objects.create(
        title="c", ticker="MSFT", direction="bullish", conviction=5, status="closed_win"
    )
    assert all(r["ticker"] != "MSFT" for r in build_exposures())
