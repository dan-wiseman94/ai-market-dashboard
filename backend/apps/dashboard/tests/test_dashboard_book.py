import datetime as dt

import pytest
from rest_framework.test import APIClient

from apps.book.models import BookSnapshot

pytestmark = pytest.mark.django_db


def test_dashboard_includes_book_default_when_empty():
    body = APIClient().get("/api/dashboard/").json()
    assert "book" in body
    assert body["book"] == {"hhi": None, "alignment": None, "as_of": None}


def test_dashboard_book_populated():
    BookSnapshot.objects.create(
        as_of_date=dt.date(2026, 6, 1),
        concentration={"hhi": 0.42}, regime_fit={"alignment": "misaligned"},
    )
    body = APIClient().get("/api/dashboard/").json()
    assert body["book"]["hhi"] == 0.42
    assert body["book"]["alignment"] == "misaligned"
    assert body["book"]["as_of"] is not None
