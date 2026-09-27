import pytest

from apps.observer.models import Notification


@pytest.mark.django_db
def test_notification_meta_round_trips_dict():
    n = Notification.objects.create(
        user=None,
        kind="error",
        title="x",
        body="",
        meta={"snapshot_id": 42, "schedule_id": 7},
    )
    assert n.meta["snapshot_id"] == 42
