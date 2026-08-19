"""Edge/error branches of the AI run task that the happy-path tests don't reach:
pure helpers, the early-return failure paths (no provider / no key / cost cap),
scenario application in mock mode, the thinking-delta stream branch, and the
cancelled-mid-run path."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from apps.ai.cost import CostCapExceededError
from apps.ai.router import ResolutionError
from apps.ai.types import DoneEvent, ThinkingDeltaEvent
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads import tasks as task_mod
from apps.threads.models import AIRun, Message, Thread, ToolCall
from apps.threads.tasks import (
    _build_request,
    _extract_text,
    _persist_tool_calls,
    _run_ai_on_message,
    run_ai_on_message,
)


def test_extract_text_reads_block_text_not_repr():
    # A "blocks" content (e.g. a Files-API document attach) surfaces its text
    # blocks — the Python repr of the dict must never reach the model.
    content = {"blocks": [{"type": "text", "text": "hi"}]}  # no top-level "text" key
    assert _extract_text(Message(content=content)) == "hi"


@pytest.mark.django_db
def test_persist_tool_calls_wraps_scalar_result_for_jsonfield():
    t = Thread.objects.create(kind="chat")
    a = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="done")
    _persist_tool_calls(
        a,
        [
            {"kind": "call", "tool_use_id": "u1", "name": "calc", "input": {"x": 1}},
            {
                "kind": "result",
                "tool_use_id": "u1",
                "ok": True,
                "result": "42",
                "error": "",
                "latency_ms": 5,
            },
        ],
    )
    tc = ToolCall.objects.get(message=a, tool_use_id="u1")
    assert tc.tool_output == {"value": "42"}  # scalar wrapped for the JSONField


@pytest.mark.django_db
def test_build_request_appends_pending_user_msg_and_carries_thinking_memory():
    p = TradingProfile.objects.create(
        name="P", style="sys", enable_thinking=True, thinking_budget=2048, enable_memory=True
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    # status != "done" => excluded from the history query => appended explicitly.
    user_msg = Message.objects.create(
        thread=t, role="user", content={"text": "hi"}, status="streaming"
    )
    with patch("apps.ai.memory.memory_dir_for_profile", return_value="/data/memory/1"):
        req = _build_request(t, user_msg, provider_name="claude")
    assert req.thinking_budget == 2048
    assert req.memory_dir == "/data/memory/1"
    assert any(getattr(cm, "content", None) == "hi" for cm in req.messages)


@pytest.mark.django_db
def test_run_ai_fails_when_no_provider_resolves():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    with patch(
        "apps.threads.tasks.resolve_provider_and_model", side_effect=ResolutionError("none")
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)
    failed = Message.objects.filter(thread=t, role="assistant", status="failed").latest(
        "created_at"
    )
    assert out == {"ok": False, "error": "no_provider", "message_id": failed.id}


@pytest.mark.django_db
def test_run_ai_fails_when_provider_config_missing():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    with patch(
        "apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)
    a = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert out == {"ok": False, "error": "no_key", "message_id": a.id}
    assert "No ProviderConfig" in a.error


@pytest.mark.django_db
def test_run_ai_fails_when_cost_cap_exceeded():
    ProviderConfig.objects.create(provider="claude", api_key="sk")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")),
        patch("apps.threads.tasks.check_daily_cap", side_effect=CostCapExceededError("over cap")),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)
    failed = Message.objects.filter(thread=t, role="assistant", status="failed").latest(
        "created_at"
    )
    assert out == {"ok": False, "error": "cost_capped", "message_id": failed.id}


def test_run_ai_applies_and_resets_scenario_in_mock_mode():
    with (
        patch("apps.core.mocks.is_mock_mode", return_value=True),
        patch("apps.core.mocks.set_scenario") as set_s,
        patch("apps.core.mocks.reset_scenario") as reset_s,
        patch("apps.threads.tasks._run_ai_on_message", return_value={"ok": True}) as inner,
    ):
        out = run_ai_on_message(thread_id=1, user_message_id=2, scenario="tooluse")
    assert out == {"ok": True}
    set_s.assert_called_once_with("tooluse")
    reset_s.assert_called_once()
    inner.assert_called_once()


def test_stream_runner_broadcasts_thinking_delta():
    seen: list[dict] = []

    async def fake_broadcast(thread_id, payload):
        seen.append(payload)

    class _Provider:
        name = "fake"

        async def run(self, _req):
            yield ThinkingDeltaEvent(text="pondering")
            yield DoneEvent()

    with patch("apps.threads.tasks._broadcast_async", fake_broadcast):
        drive = task_mod._build_stream_runner(
            [],
            {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0},
            [],
            [],
            _Provider(),
            None,
            1,
            7,
        )
        asyncio.run(drive())

    assert any(e["event"] == "thinking_delta" and e["text"] == "pondering" for e in seen)


@pytest.mark.django_db
def test_run_ai_records_cancelled_run_when_message_flipped_during_stream():
    ProviderConfig.objects.create(provider="claude", api_key="sk")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    def noop_runner(*a, **k):
        async def drive():
            return None

        return drive

    def flip_to_cancelled(message_id):
        # clear_stop runs synchronously (post-stream, pre-refresh), so this write
        # is visible to the refresh_from_db() inside _run_ai_on_message — unlike an
        # async-context write, which would land on a separate connection.
        Message.objects.filter(id=message_id).update(status="failed", error="cancelled")

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", noop_runner),
        patch("apps.threads.tasks.clear_stop", side_effect=flip_to_cancelled),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)

    a = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert out == {"ok": False, "error": "cancelled", "message_id": a.id}
    run = AIRun.objects.get(message=a)
    assert run.status == "failed"
    assert run.error == "cancelled"


@pytest.mark.django_db
def test_run_ai_stop_flag_aborts_stream_via_should_stop():
    """A set stop flag makes the _should_stop poll return True and the loop breaks."""
    ProviderConfig.objects.create(provider="claude", api_key="sk")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    async def fake_stream(self, req):
        from apps.ai.types import TextDelta

        for i in range(5):
            yield TextDelta(text=f"t{i}")
        yield DoneEvent()

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")),
        patch("apps.ai.providers.claude.ClaudeProvider.run", fake_stream),
        patch("apps.threads.tasks.is_stop_requested", return_value=True),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)

    a = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert out == {"ok": True, "message_id": a.id}
    assert a.content.get("text") == ""  # aborted before any delta was buffered


@pytest.mark.django_db
def test_run_ai_emits_capability_warning_for_unsupported_features():
    """openai + extended-thinking => a gap => a best-effort capability warning."""
    ProviderConfig.objects.create(provider="openai", api_key="sk")  # type: ignore[misc]
    p = TradingProfile.objects.create(
        name="P", style="x", enable_thinking=True, thinking_budget=1024
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    def noop_runner(*a, **k):
        async def drive():
            return None

        return drive

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("openai", "gpt-x")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", noop_runner),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)

    assert out["ok"] is True
    sys_msg = Message.objects.filter(thread=t, role="system").latest("created_at")
    assert sys_msg.content.get("kind") == "capability_warning"
