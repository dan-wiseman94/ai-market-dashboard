"""Minimal async WebSocket client for E2E tests.

Pattern:

    wc = await WsClient.connect(f"{ws_base}/ws/threads/{tid}/")
    # ... trigger backend action via httpx ...
    await wc.wait_for_event("message_done", timeout=10.0)
    wc.assert_sequence(["message_started", "text_delta", "message_done"])
    await wc.close()

``assert_sequence`` is subset-style: extra events between expected types are OK.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any


class WsClient:
    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self._events: list[dict] = []
        self._event_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    @classmethod
    async def connect(cls, url: str) -> WsClient:
        import websockets

        conn = await websockets.connect(url, open_timeout=5, close_timeout=5)
        wc = cls(conn)
        await wc.start()
        return wc

    async def start(self) -> None:
        self._task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        try:
            while True:
                payload = await self.conn.recv()
                try:
                    event = json.loads(payload)
                except Exception:
                    event = {"type": "unparseable", "raw": payload}
                self._events.append(event)
                await self._event_queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def wait_for_event(self, type_: str, timeout: float = 10.0) -> dict:
        deadline = asyncio.get_event_loop().time() + timeout
        for e in self._events:
            if e.get("type") == type_:
                return e
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"did not receive event of type {type_!r} within {timeout}s; "
                    f"received types={[e.get('type') for e in self._events]}"
                )
            e = await asyncio.wait_for(self._event_queue.get(), timeout=remaining)
            if e.get("type") == type_:
                return e

    def events_of(self, type_: str) -> list[dict]:
        return [e for e in self._events if e.get("type") == type_]

    def assert_sequence(self, expected_types: list[str]) -> None:
        """Subset-style sequence check: extra events between expected types are OK."""
        seen = iter(e.get("type") for e in self._events)
        for t in expected_types:
            for actual in seen:
                if actual == t:
                    break
            else:
                raise AssertionError(
                    f"expected type {t!r} not found after previous matches; "
                    f"got {[e.get('type') for e in self._events]}"
                )

    async def send_json(self, payload: dict) -> None:
        await self.conn.send(json.dumps(payload))

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.conn.close()
