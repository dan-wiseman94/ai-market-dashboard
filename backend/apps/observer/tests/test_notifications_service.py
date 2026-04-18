import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.observer.models import Notification
from apps.observer.services.notifications import notify


@pytest.mark.django_db
def test_notify_writes_row_with_defaults():
    n = notify(user_id=None, kind="observer_done", title="t", body="b", link="/x")
    assert n.id is not None
    assert n.user is None
    assert n.kind == "observer_done"
    assert n.body == "b"
    assert n.link == "/x"
    assert n.meta == {}
    assert Notification.objects.count() == 1


@pytest.mark.django_db
def test_notify_broadcasts_to_anonymous_group(settings):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
    layer = get_channel_layer()
    async_to_sync(layer.group_add)("user.anonymous.notifications", "test-channel")
    notify(user_id=None, kind="error", title="boom")
    msg = async_to_sync(layer.receive)("test-channel")
    assert msg["type"] == "notification.event"
    assert msg["payload"]["kind"] == "error"
    assert msg["payload"]["title"] == "boom"
