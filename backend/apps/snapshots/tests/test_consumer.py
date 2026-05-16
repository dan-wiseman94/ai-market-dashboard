import pytest
from channels.testing import WebsocketCommunicator
from config.asgi import application

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_snapshot_consumer_connects_and_closes():
    from channels.db import database_sync_to_async

    p = await database_sync_to_async(TradingProfile.objects.create)(name="P", style="x")
    snap = await database_sync_to_async(Snapshot.objects.create)(
        profile=p,
        includes=["quotes"],
        source="manual",
    )
    communicator = WebsocketCommunicator(application, f"/ws/snapshots/{snap.id}/")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_broadcast_section_done_event():
    from channels.db import database_sync_to_async
    from channels.layers import get_channel_layer

    p = await database_sync_to_async(TradingProfile.objects.create)(name="P", style="x")
    snap = await database_sync_to_async(Snapshot.objects.create)(
        profile=p,
        includes=["quotes"],
        source="manual",
    )
    communicator = WebsocketCommunicator(application, f"/ws/snapshots/{snap.id}/")
    connected, _ = await communicator.connect()
    assert connected

    layer = get_channel_layer()
    await layer.group_send(
        f"snapshot.{snap.id}",
        {"type": "snapshot_event", "payload": {"event": "section_done", "kind": "quotes"}},
    )

    msg = await communicator.receive_json_from(timeout=2)
    assert msg == {"event": "section_done", "kind": "quotes"}
    await communicator.disconnect()
