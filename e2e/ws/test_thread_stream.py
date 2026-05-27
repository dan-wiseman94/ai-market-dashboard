"""thread.<id> — message_started → text_delta* → message_done → cost.

Drives the **same** endpoint the UI calls: ``POST /api/threads/<id>/send/``.
(The earlier version posted to a non-existent ``/messages/`` route guarded by
``if 405: skip``, and looked the thread up via a *sync* ``Thread.objects.get``
inside an ``async def`` — which raises ``SynchronousOnlyOperation`` on ``web`` —
so it exercised nothing.) We resolve the thread over HTTP like the snapshot WS
test does, never touching the ORM from async context. On the default scenario
the worker streams ``"Mocked "`` + ``"response"`` over the ``thread.<id>`` group.
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


def _send(api_base_url: str, thread_id: int, text: str) -> httpx.Response:
    return httpx.post(
        f"{api_base_url}/api/threads/{thread_id}/send/",
        json={"text": text},
        timeout=5,
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_thread_stream_emits_started_deltas_done(ws_base_url, api_base_url, threads) -> None:
    tid = _plain_thread_id(api_base_url)
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/")
    try:
        r = _send(api_base_url, tid, "hello")
        assert r.status_code == 202, f"send failed: {r.status_code} {r.text}"

        await wc.wait_for_event("message_started", timeout=10.0)
        await wc.wait_for_event("text_delta", timeout=10.0)
        await wc.wait_for_event("message_done", timeout=15.0)
    finally:
        await wc.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_thread_stream_cost_event_after_done(ws_base_url, api_base_url, threads) -> None:
    """``cost`` is emitted after ``message_done`` for the same assistant message.

    (``parent_message_id`` is null on a plain send — it's only populated for
    Compare branches; see e2e/ws/test_compare_branch_costs.py for that path.)
    """
    tid = _plain_thread_id(api_base_url)
    wc = await WsClient.connect(f"{ws_base_url}/ws/threads/{tid}/")
    try:
        r = _send(api_base_url, tid, "hi")
        assert r.status_code == 202, f"send failed: {r.status_code} {r.text}"

        done = await wc.wait_for_event("message_done", timeout=15.0)
        cost = await wc.wait_for_event("cost", timeout=5.0)
        assert cost.get("message_id") == done.get("message_id")
        assert cost.get("cost_usd") is not None
    finally:
        await wc.close()
