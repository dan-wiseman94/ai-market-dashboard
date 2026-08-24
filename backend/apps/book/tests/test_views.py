import datetime as dt

import pytest
from rest_framework.test import APIClient

from apps.book.models import BookSnapshot

pytestmark = pytest.mark.django_db


def test_current_empty_null():
    assert APIClient().get("/api/book/current/").json() is None


def test_current_returns_latest():
    BookSnapshot.objects.create(as_of_date=dt.date(2026, 6, 1), concentration={"hhi": 0.4})
    body = APIClient().get("/api/book/current/").json()
    assert body["concentration"]["hhi"] == 0.4
    assert "id" in body


def test_recompute_invokes_compute(monkeypatch):
    from apps.book import views

    monkeypatch.setattr(
        views,
        "compute_and_store_book",
        lambda: BookSnapshot.objects.create(as_of_date=dt.date(2026, 6, 2)),
    )
    resp = APIClient().post("/api/book/recompute/")
    assert resp.status_code == 200
    # The stub ran (its row exists) and the response serializes that snapshot.
    assert BookSnapshot.objects.filter(as_of_date=dt.date(2026, 6, 2)).exists()
    assert resp.json()["as_of_date"] == "2026-06-02"
