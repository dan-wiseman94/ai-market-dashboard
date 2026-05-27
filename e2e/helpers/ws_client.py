"""Minimal async WebSocket client for E2E tests.

Pattern:

    wc = await WsClient.connect(f"{ws_base}/ws/threads/{tid}/")
    # ... trigger backend action via httpx ...
    await wc.wait_for_event("message_done", timeout=10.0)
    wc.assert_sequence(["message_started", "text_delta", "message_done"])
    await wc.close()

``assert_sequence`` is subset-style: extra events between expected types are OK.

Event-name key: consumers are not consistent about the discriminator key. The
notification consumer forwards ``{"type": "notification.event", ...}`` while the
thread/snapshot consumers forward the raw broadcast payload keyed under
``"event"`` (e.g. ``{"event": "message_done", ...}``). ``_event_name`` matches on
*either* key so a single helper covers every lane.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any


def _event_name(e: dict) -> str | None:
    """The event discriminator, regardless of which key the consumer used."""
    return e.get("type") or e.get("event")


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
            if _event_name(e) == type_:
                return e
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"did not receive event of type {type_!r} within {timeout}s; "
                    f"received types={[_event_name(e) for e in self._events]}"
                )
            try:
                e = await asyncio.wait_for(self._event_queue.get(), timeout=remaining)
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise TimeoutError(
                    f"did not receive event of type {type_!r} within {timeout}s; "
                    f"received types={[_event_name(e) for e in self._events]}"
                ) from exc
            if _event_name(e) == type_:
                return e

    async def wait_for_count(self, type_: str, n: int, timeout: float = 20.0) -> list[dict]:
        """Wait until at least ``n`` events of ``type_`` have arrived; return all matches.

        ``wait_for_event`` always returns the *first* cached match, so it can't
        collect distinct events (e.g. the two ``cost`` events of a Compare run);
        poll the accumulating buffer instead.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            matches = self.events_of(type_)
            if len(matches) >= n:
                return matches
            if deadline - asyncio.get_event_loop().time() <= 0:
                raise TimeoutError(
                    f"received {len(matches)}/{n} event(s) of type {type_!r} within "
                    f"{timeout}s; received types={[_event_name(e) for e in self._events]}"
                )
            await asyncio.sleep(0.2)

    def events_of(self, type_: str) -> list[dict]:
        return [e for e in self._events if _event_name(e) == type_]

    def assert_sequence(self, expected_types: list[str]) -> None:
        """Subset-style sequence check: extra events between expected types are OK."""
        seen = iter(_event_name(e) for e in self._events)
        for t in expected_types:
            for actual in seen:
                if actual == t:
                    break
            else:
                raise AssertionError(
                    f"expected type {t!r} not found after previous matches; "
                    f"got {[_event_name(e) for e in self._events]}"
                )

    async def send_json(self, payload: dict) -> None:
        await self.conn.send(json.dumps(payload))

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self.conn.close()
