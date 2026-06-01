import pytest

from apps.book.models import BookSnapshot
from apps.book.services import compute
from apps.observer.models import Notification
from apps.thesis.models import Thesis

pytestmark = pytest.mark.django_db


def _seed_concentrated():
    Thesis.objects.create(title="a", ticker="NVDA", direction="bullish", conviction=5, status="open")


def test_compute_and_store_persists_one_per_day(monkeypatch):
    monkeypatch.setattr(compute, "book_narrative", lambda *a, **k: "")
    _seed_concentrated()
    snap = compute.compute_and_store_book()
    assert snap.concentration["total_abs"] == 5.0
    snap2 = compute.compute_and_store_book()  # idempotent same-day claim
    assert BookSnapshot.objects.count() == 1
    assert snap2.as_of_date == snap.as_of_date


def test_no_alert_on_first_snapshot(monkeypatch):
    monkeypatch.setattr(compute, "book_narrative", lambda *a, **k: "")
    _seed_concentrated()
    compute.compute_and_store_book()
    assert Notification.objects.filter(kind="book").count() == 0
