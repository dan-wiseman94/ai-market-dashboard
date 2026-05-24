"""ASGI config — HTTP + WebSocket routing through Channels."""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

from config.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Validate the Origin header against ALLOWED_HOSTS to block cross-site
        # WebSocket hijacking. Permissive in dev (ALLOWED_HOSTS=["*"]); enforced
        # in prod where ALLOWED_HOSTS is restricted.
        "websocket": AllowedHostsOriginValidator(URLRouter(websocket_urlpatterns)),
    }
)
