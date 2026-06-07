import datetime as dt

import pytest

from apps.book.models import BookSnapshot
from apps.observer.briefing.services.assemble import _book_section

pytestmark = pytest.mark.django_db


def test_book_section_default_when_empty():
    assert _book_section() == {"concentration": None, "regime_fit": None, "top_risk": None}


def test_book_section_populated():
    BookSnapshot.objects.create(
        as_of_date=dt.date(2026, 6, 1),
        concentration={"hhi": 0.4, "top_n_share": 0.7},
        regime_fit={"alignment": "misaligned", "note": "net-long into risk-off"},
        narrative="Concentrated and fighting the tape.",
    )
    out = _book_section()
    assert out["regime_fit"]["alignment"] == "misaligned"
    assert out["top_risk"] == "Concentrated and fighting the tape."
