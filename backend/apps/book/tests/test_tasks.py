import pytest

from apps.book import tasks

pytestmark = pytest.mark.django_db


def test_snapshot_daily_invokes_compute(monkeypatch):
    calls = []

    class _S:
        id = 5

    monkeypatch.setattr(tasks, "compute_and_store_book", lambda: (calls.append(1), _S())[1])
    assert tasks.snapshot_daily.run() == 5
    assert len(calls) == 1
