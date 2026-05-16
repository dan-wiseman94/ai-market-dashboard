"""Per-thread WebSocket channel."""

from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ThreadConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.thread_id = int(self.scope["url_route"]["kwargs"]["thread_id"])
        self.group_name = f"thread.{self.thread_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def thread_event(self, event: dict[str, Any]) -> None:
        await self.send_json(event["payload"])
