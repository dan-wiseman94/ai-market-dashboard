"""WebSocket consumer for the notification bell."""
from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        # v1: no auth — everyone subscribes to the anonymous group.
        self.group_name = "user.anonymous.notifications"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_event(self, event: dict[str, Any]) -> None:
        await self.send_json({"type": "notification.event", "payload": event["payload"]})
