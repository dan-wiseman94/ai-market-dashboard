"""Extended thinking: thinking_delta* precedes text_delta*.

Uses the ``thinking-heavy`` scenario; ``run_ai_on_message`` re-applies the
request's scenario in the worker process (threads/tasks.py + views.py forward
``scenario=``). Real ``/send/`` endpoint, HTTP id lookup (no sync-ORM-in-async
on web).
"""

from __future__ import annotations

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
async def test_thinking_deltas_precede_text(ws_base_url, api_base_url, threads) -> None:
    tid = _plain_thread_id(api_base_url)
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{tid}/send/",
            json={"text": "think deep"},
            timeout=5,
            headers={"X-E2E-Scenario": "thinking-heavy"},
        )
        assert r.status_code == 202, f"send failed: {r.status_code} {r.text}"
        await wc.wait_for_event("thinking_delta", timeout=15.0)
        await wc.wait_for_event("text_delta", timeout=15.0)
        first_text = min(i for i, e in enumerate(wc._events) if e.get("event") == "text_delta")
        last_think = max(i for i, e in enumerate(wc._events) if e.get("event") == "thinking_delta")
        assert last_think < first_text
    finally:
        await wc.close()
