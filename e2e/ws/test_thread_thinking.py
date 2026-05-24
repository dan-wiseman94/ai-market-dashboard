"""Extended thinking: thinking_delta* precedes text_delta*."""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_thinking_deltas_precede_text(ws_base_url, api_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{t.id}/messages/",
            json={"text": "think deep"},
            timeout=5,
            headers={"X-E2E-Scenario": "thinking-heavy"},
        )
        if r.status_code == 405:
            pytest.skip("POST /threads/<id>/messages/ not registered in this build")
        await wc.wait_for_event("thinking_delta", timeout=15.0)
        await wc.wait_for_event("text_delta", timeout=15.0)
        first_text = min(i for i, e in enumerate(wc._events) if e.get("type") == "text_delta")
        last_think = max(i for i, e in enumerate(wc._events) if e.get("type") == "thinking_delta")
        assert last_think < first_text
    finally:
        await wc.close()
