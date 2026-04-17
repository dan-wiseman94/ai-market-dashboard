"""Channels WebSocket URL routing."""
from django.urls import path

from apps.core.consumers import PingConsumer

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
]
