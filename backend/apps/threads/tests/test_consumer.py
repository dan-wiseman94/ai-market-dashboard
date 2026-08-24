import pytest
from channels.testing import WebsocketCommunicator
from config.asgi import application


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_thread_consumer_forwards_text_delta():
    from channels.db import database_sync_to_async
    from channels.layers import get_channel_layer

    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    p = await database_sync_to_async(TradingProfile.objects.create)(name="P", style="x")
    t = await database_sync_to_async(Thread.objects.create)(kind="consult", profile=p, title="x")

    communicator = WebsocketCommunicator(application, f"/ws/threads/{t.id}/")
    connected, _ = await communicator.connect()
    assert connected

    # First frame announces the replay-buffer geometry (sourced from event_log's
    # constants — the client heuristic derives from it, not mirrored literals).
    # Exact equality also proves it carries no seq: it never enters the replay
    # buffer, so a reconnect with ?since= can never replay or dedupe it.
    from apps.threads.event_log import MAX_EVENTS, TTL_SECONDS

    cfg = await communicator.receive_json_from(timeout=2)
    assert cfg == {"type": "replay_config", "buffer": MAX_EVENTS, "ttl_seconds": TTL_SECONDS}

    layer = get_channel_layer()
    await layer.group_send(
        f"thread.{t.id}",
        {
            "type": "thread_event",
            "payload": {"event": "text_delta", "message_id": 1, "text": "Hello"},
        },
    )
    msg = await communicator.receive_json_from(timeout=2)
    assert msg == {"event": "text_delta", "message_id": 1, "text": "Hello"}
    await communicator.disconnect()
