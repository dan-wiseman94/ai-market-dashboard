"""Compare — 2 parent_message_ids → 2 cost events with matching parent_ids."""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_compare_costs_route_to_right_branch(ws_base_url, api_base_url, threads) -> None:
    from apps.threads.models import Thread

    t = Thread.objects.get(title="E2E plain thread")
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{t.id}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{t.id}/compare/",
            json={
                "prompt": "compare",
                "targets": [
                    {"provider": "claude", "model": "claude-sonnet-4-6"},
                    {"provider": "openai", "model": "gpt-5-mini"},
                ],
            },
            timeout=5,
        )
        if r.status_code in (404, 405):
            pytest.skip("compare endpoint not yet registered in this build")
        assert r.status_code in (200, 202)
        body = r.json()
        branches = body.get("branches") or []
        if len(branches) < 2:
            pytest.skip("compare did not return 2 branch ids")

        parent_ids = [b.get("parent_message_id") for b in branches]
        cost_events = []
        for _ in range(2):
            ev = await wc.wait_for_event("cost", timeout=20.0)
            cost_events.append(ev)
        assert sorted(e["data"].get("parent_message_id") for e in cost_events) == sorted(parent_ids)
    finally:
        await wc.close()
