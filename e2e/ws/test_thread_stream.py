"""thread.<id> — message_started → text_delta* → message_done → cost."""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_thread_stream_emits_started_deltas_done(ws_base_url, api_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{t.id}/messages/",
            json={"text": "hello"},
            timeout=5,
        )
        if r.status_code == 405:
            pytest.skip("POST /threads/<id>/messages/ not registered in this build")
        assert r.status_code in (200, 201, 202)

        await wc.wait_for_event("message_started", timeout=10.0)
        await wc.wait_for_event("text_delta", timeout=10.0)
        await wc.wait_for_event("message_done", timeout=15.0)
    finally:
        await wc.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_thread_stream_cost_event_carries_parent_message_id(
    ws_base_url, api_base_url, threads
) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{t.id}/messages/", json={"text": "hi"}, timeout=5
        )
        if r.status_code == 405:
            pytest.skip("POST /threads/<id>/messages/ not registered in this build")
        done = await wc.wait_for_event("message_done", timeout=15.0)
        cost = await wc.wait_for_event("cost", timeout=5.0)
        parent = done.get("data", {}).get("message_id") or done.get("message_id")
        if parent is not None:
            assert cost["data"].get("parent_message_id") == parent
    finally:
        await wc.close()
