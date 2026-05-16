"""Unit test for the WsClient helper — uses a fake connection (no socket)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest


class _FakeConnection:
    """Minimal stand-in for websockets.WebSocketClientProtocol."""

    def __init__(self, messages: list[str]) -> None:
        self._q: asyncio.Queue[str] = asyncio.Queue()
        for m in messages:
            self._q.put_nowait(m)

    async def recv(self) -> str:
        return await self._q.get()

    async def send(self, _payload: str) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_ws_client_collects_events() -> None:
    from e2e.helpers.ws_client import WsClient

    messages = [
        json.dumps({"type": "message_started", "data": {}}),
        json.dumps({"type": "text_delta", "data": {"text": "hi"}}),
        json.dumps({"type": "done", "data": {}}),
    ]
    wc = WsClient(_FakeConnection(messages))
    await wc.start()
    ev = await wc.wait_for_event("text_delta", timeout=1.0)
    assert ev["data"]["text"] == "hi"
    await wc.wait_for_event("done", timeout=1.0)
    await wc.close()


@pytest.mark.asyncio
async def test_ws_client_assert_sequence() -> None:
    from e2e.helpers.ws_client import WsClient

    messages = [
        json.dumps({"type": "a", "data": {}}),
        json.dumps({"type": "b", "data": {}}),
        json.dumps({"type": "c", "data": {}}),
    ]
    wc = WsClient(_FakeConnection(messages))
    await wc.start()
    await asyncio.sleep(0.05)
    wc.assert_sequence(["a", "b", "c"])
    await wc.close()


@pytest.mark.asyncio
async def test_ws_client_assert_sequence_subset() -> None:
    """Extra events between expected types are OK."""
    from e2e.helpers.ws_client import WsClient

    messages = [
        json.dumps({"type": "started"}),
        json.dumps({"type": "noise"}),
        json.dumps({"type": "delta"}),
        json.dumps({"type": "more_noise"}),
        json.dumps({"type": "done"}),
    ]
    wc = WsClient(_FakeConnection(messages))
    await wc.start()
    await asyncio.sleep(0.05)
    wc.assert_sequence(["started", "delta", "done"])
    await wc.close()


@pytest.mark.asyncio
async def test_ws_client_wait_for_event_times_out() -> None:
    from e2e.helpers.ws_client import WsClient

    wc = WsClient(_FakeConnection([]))
    await wc.start()
    with pytest.raises(TimeoutError):
        await wc.wait_for_event("never_arrives", timeout=0.1)
    await wc.close()


def _example_event() -> Any:
    """Anchor for static analysis — referenced indirectly above."""
    return {"type": "noop"}
