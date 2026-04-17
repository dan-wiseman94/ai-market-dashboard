"""Channels WebSocket URL routing."""
from apps.core.consumers import PingConsumer
from django.urls import path

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
]
