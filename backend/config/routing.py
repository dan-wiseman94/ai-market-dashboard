"""Channels WebSocket URL routing."""
from django.urls import path

from apps.core.consumers import PingConsumer
from apps.snapshots.consumers import SnapshotConsumer

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
    path("ws/snapshots/<int:snapshot_id>/", SnapshotConsumer.as_asgi()),
]
