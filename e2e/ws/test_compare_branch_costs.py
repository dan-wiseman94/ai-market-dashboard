"""Compare — one user turn fans out to N branches; each emits its own ``cost``.

Both branches share the same ``parent_message_id`` (the single user message)
and are distinguished by their own assistant ``message_id`` — that's how the
Compare UI routes each ``cost`` to the right branch tab. The earlier version
posted the wrong body shape (``prompt``/``targets`` instead of ``text``/
``branches``), looked the thread up via sync-ORM-in-async, and asserted
*distinct* parent ids (there's only one).

We fan out across two **Claude** models rather than claude+openai: under the
e2e ``MOCK_EXTERNAL`` overlay the OpenAI SDK client raises at construction when
no api_key is seeded (``OpenAIError: Missing credentials``), so an openai branch
never reaches the mock and silently never finishes. Two claude branches both
stream the default ``"Mocked response"`` from the worker.
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
async def test_compare_costs_route_to_right_branch(ws_base_url, api_base_url, threads) -> None:
    tid = _plain_thread_id(api_base_url)
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/")
    try:
        r = httpx.post(
            f"{api_base_url}/api/threads/{tid}/compare/",
            json={
                "text": "compare these",
                "branches": [
                    {"provider": "claude", "model": "claude-sonnet-4-6"},
                    {"provider": "claude", "model": "claude-opus-4-8"},
                ],
            },
            timeout=5,
        )
        assert r.status_code == 202, f"compare failed: {r.status_code} {r.text}"
        body = r.json()
        user_message_id = body["user_message_id"]
        assert len(body.get("branches") or []) == 2, body

        cost_events = await wc.wait_for_count("cost", 2, timeout=25.0)

        # Both costs hang off the single user turn …
        assert all(e.get("parent_message_id") == user_message_id for e in cost_events), cost_events
        # … but each branch has its own assistant message_id (that's the routing key).
        assert len({e.get("message_id") for e in cost_events}) == 2, cost_events
    finally:
        await wc.close()
