"""Tool-use loop: tool_call → tool_result → text_delta → message_done."""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_tool_use_loop_emits_tool_call_and_tool_result(
    ws_base_url, api_base_url, threads
) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{t.id}/messages/",
            json={"text": "use a tool"},
            timeout=5,
            headers={"X-E2E-Scenario": "tool-use-loop"},
        )
        if r.status_code == 405:
            pytest.skip("POST /threads/<id>/messages/ not registered in this build")
        await wc.wait_for_event("tool_call", timeout=15.0)
        await wc.wait_for_event("tool_result", timeout=15.0)
        await wc.wait_for_event("message_done", timeout=15.0)
    finally:
        await wc.close()
