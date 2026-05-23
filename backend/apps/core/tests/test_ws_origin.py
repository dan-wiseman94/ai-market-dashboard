"""WebSocket connections must validate the Origin header.

Without this, any page the user visits can open ws://localhost:8000/ws/... and
talk to the app (cross-site WebSocket hijacking). AllowedHostsOriginValidator
enforces the Origin host against ALLOWED_HOSTS.
"""

import pytest
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator
from channels.testing import WebsocketCommunicator
from django.test import override_settings


def test_asgi_websocket_is_origin_validated():
    from config.asgi import application

    ws = application.application_mapping["websocket"]
    assert isinstance(ws, OriginValidator)


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["testserver"])
async def test_ws_rejects_foreign_origin():
    # Build the validator after override so it captures the restricted host list.
    from config.routing import websocket_urlpatterns

    app = AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns))
    comm = WebsocketCommunicator(app, "/ws/ping/", headers=[(b"origin", b"http://evil.example")])
    connected, _ = await comm.connect()
    assert connected is False
    await comm.disconnect()


@pytest.mark.asyncio
@override_settings(ALLOWED_HOSTS=["testserver"])
async def test_ws_allows_matching_origin():
    from config.routing import websocket_urlpatterns

    app = AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns))
    comm = WebsocketCommunicator(app, "/ws/ping/", headers=[(b"origin", b"http://testserver")])
    connected, _ = await comm.connect()
    assert connected is True
    await comm.disconnect()
