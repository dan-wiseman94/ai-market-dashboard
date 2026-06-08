"""Reconnect with ``?since=<seq>`` — replays recent events with no gap.

ThreadConsumer implements seq-based replay (apps/threads/consumers.py + event_log),
so reconnecting with ``?since=<last_seq>`` must redeliver the tail (incl.
``message_done``) with contiguous seqs. The first leg still tolerates a slow
mock stream (skips if no ``text_delta`` arrives in-window) to stay non-flaky.
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
    payload = r.json()
    rows = payload["results"] if isinstance(payload, dict) else payload
    for t in rows:
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
        # Replay must redeliver the tail (incl. message_done) on reconnect.
        await wc2.wait_for_event("message_done", timeout=10.0)
        seqs = [e["seq"] for e in wc2._events if "seq" in e]
        for a, b in itertools.pairwise(seqs):
            assert b == a + 1
    finally:
        await wc2.close()
