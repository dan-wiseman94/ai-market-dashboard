"""Per-thread WebSocket channel."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ThreadConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.thread_id = int(self.scope["url_route"]["kwargs"]["thread_id"])
        self.group_name = f"thread.{self.thread_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        from apps.threads.event_log import MAX_EVENTS, TTL_SECONDS, replay_since

        # First frame, before any replay: the server's replay-buffer geometry, so
        # the client derives its duplicate-vs-counter-restart heuristic from the
        # source of truth instead of mirrored literals. Sent directly (never via
        # event_log.record) — it must not consume a seq or enter the buffer.
        await self.send_json(
            {"type": "replay_config", "buffer": MAX_EVENTS, "ttl_seconds": TTL_SECONDS}
        )
        # Reconnect replay: a client that dropped can pass ?since=<seq> to receive
        # the buffered events it missed before live streaming resumes. Joining the
        # group before replaying means a concurrent live event is at worst a
        # duplicate (same seq), never a gap — the client dedupes on seq.
        since = self._since()
        if since is not None:
            for ev in await sync_to_async(replay_since)(self.thread_id, since):
                await self.send_json(ev)

    def _since(self) -> int | None:
        raw = parse_qs(self.scope.get("query_string", b"").decode()).get("since", [None])[0]
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def thread_event(self, event: dict[str, Any]) -> None:
        await self.send_json(event["payload"])
