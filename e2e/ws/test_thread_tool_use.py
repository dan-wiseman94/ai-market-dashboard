"""Tool-use loop: tool_call → tool_result → text_delta → message_done.

SKIPPED: requires the ``tool-use-loop`` scenario to reach the *worker*, but the
scenario lives in a web-process ContextVar the worker never sees
(apps/core/mocks/__init__.py), so the worker streams the plain default response
and no ``tool_call`` is emitted. The body below is otherwise correct (real
``/send/`` endpoint, HTTP id lookup) — drop the skip once the worker honors
X-E2E-Scenario.
"""

from __future__ import annotations

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
@pytest.mark.skip(reason="scenario→worker propagation gap: worker never sees tool-use-loop")
async def test_tool_use_loop_emits_tool_call_and_tool_result(
    ws_base_url, api_base_url, threads
) -> None:
    tid = _plain_thread_id(api_base_url)
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{tid}/send/",
            json={"text": "use a tool"},
            timeout=5,
            headers={"X-E2E-Scenario": "tool-use-loop"},
        )
        assert r.status_code == 202, f"send failed: {r.status_code} {r.text}"
        await wc.wait_for_event("tool_call", timeout=15.0)
        await wc.wait_for_event("tool_result", timeout=15.0)
        await wc.wait_for_event("message_done", timeout=15.0)
    finally:
        await wc.close()
