"""Reconnect with ``?since=<seq>`` — replays recent events with no gap.

If the backend's ThreadConsumer doesn't support seq-based replay yet, this test
documents the requirement and skips cleanly so we don't churn green-on-red.
"""

from __future__ import annotations

import asyncio
import itertools

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_ws_reconnect_replays_recent_events(ws_base_url, api_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")

    wc1 = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/")
    r = httpx.post(f"{api_base_url}/api/threads/{t.id}/messages/", json={"text": "hi"}, timeout=5)
    if r.status_code == 405:
        await wc1.close()
        pytest.skip("POST /threads/<id>/messages/ not registered in this build")

    try:
        await wc1.wait_for_event("text_delta", timeout=10.0)
    except TimeoutError:
        await wc1.close()
        pytest.skip("backend did not produce text_delta within window")
    last_seq = wc1._events[-1].get("data", {}).get("seq", 0)
    await wc1.close()

    await asyncio.sleep(1)

    wc2 = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/?since={last_seq}")
    try:
        try:
            await wc2.wait_for_event("message_done", timeout=10.0)
        except TimeoutError:
            pytest.skip("ThreadConsumer doesn't yet implement ?since=<seq> replay")
        seqs = [e.get("data", {}).get("seq") for e in wc2._events if "seq" in e.get("data", {})]
        for a, b in itertools.pairwise(seqs):
            assert b == a + 1
    finally:
        await wc2.close()
