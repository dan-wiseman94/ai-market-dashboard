"""Stop must actually abort an in-flight stream, not just discard the final write.

Before: the drive loop drained the provider to completion (full generation + billing)
and only suppressed the DB write. These tests pin the real behavior: the loop checks
a stop predicate, breaks early, and closes the provider stream.
"""

import asyncio

import pytest
from rest_framework.test import APIClient

from apps.ai.types import DoneEvent, TextDelta
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread
from apps.threads.stop import is_stop_requested
from apps.threads.tasks import _build_stream_runner


class _FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.closed = False
        self.yielded = 0

    async def run(self, _req):
        try:
            for i in range(10):
                self.yielded += 1
                yield TextDelta(text=f"t{i}")
            yield DoneEvent()
        finally:
            self.closed = True


@pytest.fixture(autouse=True)
def _no_broadcast(monkeypatch):
    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr("apps.threads.tasks._broadcast_async", _noop)


def _runner(provider, buffer, should_stop):
    counts = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
    return _build_stream_runner(buffer, counts, [], [], provider, None, 1, 1, should_stop)


def test_drive_aborts_early_when_should_stop_flips():
    provider = _FakeProvider()
    buffer: list[str] = []
    checks = {"n": 0}

    def should_stop() -> bool:
        checks["n"] += 1
        return checks["n"] > 2  # allow two events, then stop

    asyncio.run(_runner(provider, buffer, should_stop)())

    assert buffer == ["t0", "t1"], "stream should stop after two deltas"
    assert provider.yielded < 10, "provider must not be drained to completion"
    assert provider.closed is True, "provider stream must be closed on abort"


def test_drive_runs_to_completion_when_never_stopped():
    provider = _FakeProvider()
    buffer: list[str] = []

    asyncio.run(_runner(provider, buffer, lambda: False)())

    assert len(buffer) == 10
    assert provider.closed is True


@pytest.mark.django_db
def test_stop_endpoint_requests_stop_flag(monkeypatch):
    import fakeredis

    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr("apps.threads.stop._redis", lambda: client)

    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="streaming")

    resp = APIClient().post(f"/api/threads/{t.id}/stop/{m.id}/", format="json")
    assert resp.status_code == 200
    assert is_stop_requested(m.id) is True
