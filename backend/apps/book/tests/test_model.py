import datetime as dt

import pytest

from apps.book.models import BookSnapshot
from apps.book.services.compute import current_book

pytestmark = pytest.mark.django_db


def test_current_book_latest():
    BookSnapshot.objects.create(as_of_date=dt.date(2026, 5, 31))
    latest = BookSnapshot.objects.create(as_of_date=dt.date(2026, 6, 1))
    assert current_book().id == latest.id


def test_current_book_none():
    assert current_book() is None
