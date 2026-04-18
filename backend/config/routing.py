"""Channels WebSocket URL routing."""
from apps.core.consumers import PingConsumer
from apps.observer.consumers import NotificationsConsumer
from apps.snapshots.consumers import SnapshotConsumer
from apps.threads.consumers import ThreadConsumer
from django.urls import path

websocket_urlpatterns = [
    path("ws/ping/", PingConsumer.as_asgi()),
    path("ws/notifications/", NotificationsConsumer.as_asgi()),
    path("ws/snapshots/<int:snapshot_id>/", SnapshotConsumer.as_asgi()),
    path("ws/threads/<int:thread_id>/", ThreadConsumer.as_asgi()),
]
