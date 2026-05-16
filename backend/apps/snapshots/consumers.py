"""Per-snapshot WebSocket channel."""

from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class SnapshotConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.snapshot_id = int(self.scope["url_route"]["kwargs"]["snapshot_id"])
        self.group_name = f"snapshot.{self.snapshot_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def snapshot_event(self, event: dict[str, Any]) -> None:
        """Receive group_send with type=snapshot_event; forward payload to the client."""
        await self.send_json(event["payload"])
