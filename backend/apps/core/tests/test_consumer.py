import pytest
from channels.testing import WebsocketCommunicator
from config.asgi import application


@pytest.mark.asyncio
async def test_ping_consumer_echoes_pong():
    """A client connects to /ws/ping/, sends 'ping', receives 'pong'."""
    communicator = WebsocketCommunicator(application, "/ws/ping/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "ping"})
    reply = await communicator.receive_json_from(timeout=2)
    assert reply == {"type": "pong"}

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_ping_consumer_ignores_unknown_types():
    """Unknown message types are ignored; no reply, connection stays up."""
    communicator = WebsocketCommunicator(application, "/ws/ping/")
    connected, _ = await communicator.connect()
    assert connected

    await communicator.send_json_to({"type": "garbage"})
    assert await communicator.receive_nothing(timeout=0.5)

    await communicator.disconnect()
