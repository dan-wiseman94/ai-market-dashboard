"""Observer timeline bins messages on observer threads per day by status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.analytics.services.observer_timeline import observer_timeline
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.fixture
def observer_thread(db):
    prof = TradingProfile.objects.create(name="p", style="s")
    return Thread.objects.create(kind="observer", profile=prof, title="observer")


def _msg(thread, *, role: str, status: str, at: datetime) -> Message:
    m = Message.objects.create(thread=thread, role=role, content={"text": "x"}, status=status)
    Message.objects.filter(id=m.id).update(
        created_at=at.replace(tzinfo=UTC) if at.tzinfo is None else at,
    )
    return m


def test_timeline_buckets_assistant_done_as_success(db, observer_thread) -> None:
    day = datetime(2026, 4, 10, 14, 0, tzinfo=UTC)
    _msg(observer_thread, role="assistant", status="done", at=day)
    _msg(observer_thread, role="assistant", status="done", at=day + timedelta(hours=2))
    out = observer_timeline(
        start=day - timedelta(days=1),
        end=day + timedelta(days=1),
    )
    assert len(out) == 2
    day0 = datetime(2026, 4, 10).date().isoformat()
    row = next(r for r in out if r["date"] == day0)
    assert row["success"] == 2
    assert row["failed"] == 0
    assert row["skipped"] == 0


def test_timeline_counts_failed_and_skipped(db, observer_thread) -> None:
    day = datetime(2026, 4, 10, 14, 0, tzinfo=UTC)
    _msg(observer_thread, role="assistant", status="failed", at=day)
    _msg(observer_thread, role="system", status="done", at=day)
    out = observer_timeline(start=day - timedelta(days=1), end=day + timedelta(days=1))
    day0 = datetime(2026, 4, 10).date().isoformat()
    row = next(r for r in out if r["date"] == day0)
    assert row["failed"] == 1
    assert row["skipped"] == 1


def test_timeline_ignores_non_observer_threads(db) -> None:
    prof = TradingProfile.objects.create(name="other", style="s")
    t = Thread.objects.create(kind="consult", profile=prof)
    day = datetime(2026, 4, 10, tzinfo=UTC)
    _msg(t, role="assistant", status="done", at=day)
    out = observer_timeline(start=day - timedelta(days=1), end=day + timedelta(days=1))
    assert all(r["success"] == 0 for r in out)


def test_timeline_is_zero_filled_across_window(db) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    out = observer_timeline(
        start=now - timedelta(days=2),
        end=now + timedelta(days=1),
    )
    assert len(out) == 3
    dates = {r["date"] for r in out}
    assert dates == {
        (now - timedelta(days=2)).date().isoformat(),
        (now - timedelta(days=1)).date().isoformat(),
        now.date().isoformat(),
    }
