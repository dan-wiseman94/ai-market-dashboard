"""Streaming runs must persist partial text to the DB *during* the stream.

Before: streamed tokens lived only in the worker's in-memory ``buffer`` and were
written to ``Message.content`` only at the terminal write. A page reload mid-stream
(e.g. back/forward navigation into a thread whose run is still in flight) seeded the
bubble from the empty DB row and then re-streamed from the live socket — looking like
the AI was "regenerating" the response on every open.

These tests pin the fix: a throttled flush persists the accumulated buffer to the
streaming message, guarded on ``status='streaming'`` so a concurrent stop/finalize is
never clobbered.
"""

import asyncio

import pytest
from asgiref.sync import sync_to_async

from apps.ai.types import DoneEvent, TextDelta
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread
from apps.threads.tasks import _build_stream_runner, _make_flush_partial


@pytest.fixture(autouse=True)
def _no_broadcast(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr("apps.threads.tasks._broadcast_async", _noop)


def _run(coro):
    """Run an async coroutine, then close the DB connection opened by the flush's
    thread-sensitive executor — within the *same* event loop, so the close lands on
    the same thread that created it. Otherwise that connection lingers and blocks the
    session-end test-DB teardown ('database is being accessed by other users')."""

    def _close_conn():
        # Resolve the connection proxy *here*, inside the executor thread, so we close
        # that thread's connection (not the main thread's).
        from django.db import connection

        connection.close()

    async def _wrapped():
        try:
            return await coro
        finally:
            await sync_to_async(_close_conn)()

    return asyncio.run(_wrapped())


def _streaming_msg() -> Message:
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    return Message.objects.create(
        thread=t, role="assistant", content={"text": ""}, status="streaming"
    )


@pytest.mark.django_db(transaction=True)
def test_flush_partial_persists_buffer_to_streaming_message():
    msg = _streaming_msg()
    flush = _make_flush_partial(msg.id, ["Hello", ", ", "world"])

    _run(flush(force=True))

    msg.refresh_from_db()
    assert msg.content["text"] == "Hello, world"
    assert msg.status == "streaming"


@pytest.mark.django_db(transaction=True)
def test_flush_partial_is_noop_once_message_left_streaming():
    """A concurrent stop/finalize must not be resurrected: the flush is guarded on
    status='streaming', so a cancelled message keeps its terminal state and text."""
    msg = _streaming_msg()
    Message.objects.filter(id=msg.id).update(status="failed", error="cancelled")
    flush = _make_flush_partial(msg.id, ["late", " tokens"])

    _run(flush(force=True))

    msg.refresh_from_db()
    assert msg.status == "failed"
    assert msg.error == "cancelled"
    assert msg.content.get("text", "") == ""


@pytest.mark.django_db(transaction=True)
def test_partial_text_is_visible_mid_stream():
    """The accumulated text is readable from the DB *before* the stream completes."""
    msg = _streaming_msg()
    seen: dict[str, str] = {}

    class _FakeProvider:
        name = "fake"

        async def run(self, _req):
            yield TextDelta(text="alpha ")
            # The first delta must already be persisted by the time the next is produced.
            seen["mid"] = await sync_to_async(
                lambda: Message.objects.get(id=msg.id).content.get("text", "")
            )()
            yield TextDelta(text="beta")
            yield DoneEvent()

    buffer: list[str] = []
    counts = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    flush = _make_flush_partial(msg.id, buffer)
    drive = _build_stream_runner(
        buffer, counts, [], [], _FakeProvider(), None, msg.thread_id, msg.id, lambda: False, flush
    )

    _run(drive())

    assert seen["mid"] == "alpha ", "first delta must be persisted before the stream completes"
    msg.refresh_from_db()
    assert msg.content["text"] == "alpha beta"


@pytest.mark.django_db(transaction=True)
def test_early_break_persists_partial_text():
    """A stopped/cancelled run keeps what it streamed so far (the finally force-flush),
    instead of discarding the buffer and leaving an empty message — the failure mode
    that lost the cancelled run's output before this fix."""
    msg = _streaming_msg()

    class _FakeProvider:
        name = "fake"

        async def run(self, _req):
            yield TextDelta(text="one ")
            yield TextDelta(text="two ")
            yield TextDelta(text="three")
            yield DoneEvent()

    checks = {"n": 0}

    def should_stop() -> bool:
        checks["n"] += 1
        return checks["n"] > 2  # allow two deltas, then stop

    buffer: list[str] = []
    counts = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    flush = _make_flush_partial(msg.id, buffer)
    drive = _build_stream_runner(
        buffer, counts, [], [], _FakeProvider(), None, msg.thread_id, msg.id, should_stop, flush
    )

    _run(drive())

    msg.refresh_from_db()
    assert msg.content["text"] == "one two ", "partial text up to the stop must survive"
