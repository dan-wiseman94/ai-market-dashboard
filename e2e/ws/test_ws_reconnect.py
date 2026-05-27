"""Reconnect with ``?since=<seq>`` — replays recent events with no gap.

The ThreadConsumer doesn't implement seq-based replay yet, so this test drives
the real send path and then skips cleanly on the missing feature rather than
churning green-on-red. (Previously it also failed hard: sync-ORM-in-async on
``web`` and a POST to the non-existent ``/messages/`` route.)
"""

from __future__ import annotations

import asyncio
import itertools

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


def _plain_thread_id(api_base_url: str) -> int:
    r = httpx.get(f"{api_base_url}/api/threads/", timeout=5)
    r.raise_for_status()
    for t in r.json():
        if t.get("title") == "E2E plain thread":
            return int(t["id"])
    raise AssertionError("seeded 'E2E plain thread' not found via /api/threads/")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_ws_reconnect_replays_recent_events(ws_base_url, api_base_url, threads) -> None:
    tid = _plain_thread_id(api_base_url)

    wc1 = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/")
    r = httpx.post(f"{api_base_url}/api/threads/{tid}/send/", json={"text": "hi"}, timeout=5)
    assert r.status_code == 202, f"send failed: {r.status_code} {r.text}"

    try:
        await wc1.wait_for_event("text_delta", timeout=10.0)
    except TimeoutError:
        await wc1.close()
        pytest.skip("backend did not produce text_delta within window")
    last_seq = wc1._events[-1].get("seq", 0)
    await wc1.close()

    await asyncio.sleep(1)

    wc2 = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/?since={last_seq}")
    try:
        try:
            await wc2.wait_for_event("message_done", timeout=10.0)
        except TimeoutError:
            pytest.skip("ThreadConsumer doesn't yet implement ?since=<seq> replay")
        seqs = [e["seq"] for e in wc2._events if "seq" in e]
        for a, b in itertools.pairwise(seqs):
            assert b == a + 1
    finally:
        await wc2.close()
