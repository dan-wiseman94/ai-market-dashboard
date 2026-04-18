import pytest

from apps.observer.models import Notification


@pytest.mark.django_db
def test_notification_persists_with_v1_nullable_user():
    n = Notification.objects.create(
        user=None, kind="observer_done",
        title="Observer fired: Day Trader",
        body="Snapshot #1 captured",
        link="/threads/observer/1",
    )
    assert n.id is not None
    assert n.user is None
    assert n.kind == "observer_done"
    assert n.read_at is None
    assert n.meta == {}


@pytest.mark.django_db
def test_notification_meta_round_trips_dict():
    n = Notification.objects.create(
        user=None, kind="error", title="x", body="",
        meta={"snapshot_id": 42, "schedule_id": 7},
    )
    assert n.meta["snapshot_id"] == 42
