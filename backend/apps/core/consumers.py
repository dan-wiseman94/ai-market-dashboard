"""Smoke-test WebSocket consumer. Real domain consumers live in their own apps."""
from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class PingConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        await self.accept()

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})
