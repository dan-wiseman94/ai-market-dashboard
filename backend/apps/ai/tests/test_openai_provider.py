import asyncio
from unittest.mock import MagicMock, patch

import pytest

from apps.ai.providers.openai import OpenAIProvider
from apps.ai.types import (
    ChatMessage,
    DoneEvent,
    RunRequest,
    TextDelta,
    ToolCallEvent,
    ToolResultEvent,
    UsageEvent,
)


class _FakeOpenAIStream:
    """Mimics openai.AsyncStream yielding ChatCompletionChunks."""

    def __init__(self, text_chunks, usage):
        self._text_chunks = text_chunks
        self._usage = usage

    def __aiter__(self):
        async def gen():
            for c in self._text_chunks:
                chunk = MagicMock()
                choice = MagicMock()
                choice.delta.content = c
                chunk.choices = [choice]
                chunk.usage = None
                yield chunk
            # Final chunk with usage (include_usage=True causes OpenAI to stream usage last)
            final = MagicMock()
            final.choices = []
            final.usage = MagicMock(
                prompt_tokens=self._usage["input"],
                completion_tokens=self._usage["output"],
                prompt_tokens_details=MagicMock(cached_tokens=self._usage.get("cached", 0)),
            )
            yield final

        return gen()


@pytest.mark.asyncio
async def test_openai_streams_deltas_and_usage():
    fake = MagicMock()

    async def fake_create(**kwargs):
        return _FakeOpenAIStream(
            ["Hello", " ", "world"],
            {"input": 80, "output": 20, "cached": 10},
        )

    fake.chat.completions.create = fake_create
    with patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="You help.",
            messages=[ChatMessage(role="user", content="hi")],
        )
        events = []
        async for evt in provider.run(req):
            events.append(evt)

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "Hello world"

    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.usage.input_tokens == 80
    assert usage.usage.output_tokens == 20
    assert usage.usage.cached_tokens == 10

    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_openai_normalizes_system_prompt_as_message():
    """OpenAI expects system as a message, not a top-level block like Claude."""
    captured = {}

    fake = MagicMock()

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return _FakeOpenAIStream(["ok"], {"input": 1, "output": 1})

    fake.chat.completions.create = fake_create
    with patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="YOU_ARE_A_TRADER",
            messages=[ChatMessage(role="user", content="hi")],
        )
        async for _ in provider.run(req):
            pass

    sent = captured["messages"]
    assert sent[0] == {"role": "system", "content": "YOU_ARE_A_TRADER"}
    assert sent[1] == {"role": "user", "content": "hi"}


class _FakeToolCallStream:
    """First round: stream a tool_call split across deltas, finish_reason=tool_calls."""

    def __aiter__(self):
        async def gen():
            # fragment 1: id + name, arguments start
            c1 = MagicMock()
            ch1 = MagicMock()
            ch1.delta.content = None
            tc1 = MagicMock()
            tc1.index = 0
            tc1.id = "call_1"
            tc1.function.name = "get_quote"
            tc1.function.arguments = '{"ti'
            ch1.delta.tool_calls = [tc1]
            ch1.finish_reason = None
            c1.choices = [ch1]
            c1.usage = None
            yield c1
            # fragment 2: more arguments, no id/name
            c2 = MagicMock()
            ch2 = MagicMock()
            ch2.delta.content = None
            tc2 = MagicMock()
            tc2.index = 0
            tc2.id = None
            tc2.function.name = None
            tc2.function.arguments = 'cker": "AAPL"}'
            ch2.delta.tool_calls = [tc2]
            ch2.finish_reason = "tool_calls"
            c2.choices = [ch2]
            c2.usage = MagicMock(
                prompt_tokens=50,
                completion_tokens=5,
                prompt_tokens_details=MagicMock(cached_tokens=0),
            )
            yield c2

        return gen()


class _FakeTextStream:
    """Second round: plain text answer, finish_reason=stop."""

    def __aiter__(self):
        async def gen():
            c = MagicMock()
            ch = MagicMock()
            ch.delta.content = "AAPL is at 200."
            ch.delta.tool_calls = None
            ch.finish_reason = "stop"
            c.choices = [ch]
            c.usage = MagicMock(
                prompt_tokens=70,
                completion_tokens=8,
                prompt_tokens_details=MagicMock(cached_tokens=0),
            )
            yield c

        return gen()


@pytest.mark.asyncio
async def test_openai_tool_loop_dispatches_and_continues():
    streams = [_FakeToolCallStream(), _FakeTextStream()]
    captured_calls = []
    fake = MagicMock()

    async def fake_create(**kwargs):
        captured_calls.append(kwargs)
        return streams.pop(0)

    fake.chat.completions.create = fake_create

    fake_toolset = MagicMock()
    fake_toolset.run.return_value = {"ok": True, "result": {"last": 200}}

    with (
        patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake),
        patch("apps.ai.providers.openai._resolve_toolset", return_value=fake_toolset),
    ):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="You help.",
            messages=[ChatMessage(role="user", content="quote AAPL")],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "get_quote", "description": "", "parameters": {}},
                }
            ],
        )
        events = [evt async for evt in provider.run(req)]

    fake_toolset.run.assert_called_once_with("get_quote", {"ticker": "AAPL"})

    call_evt = next(e for e in events if isinstance(e, ToolCallEvent))
    assert call_evt.name == "get_quote"
    assert call_evt.input == {"ticker": "AAPL"}
    assert call_evt.tool_use_id == "call_1"

    res_evt = next(e for e in events if isinstance(e, ToolResultEvent))
    assert res_evt.ok is True

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "AAPL is at 200."

    assert len(captured_calls) == 2
    second_msgs = captured_calls[1]["messages"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1" for m in second_msgs)

    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.usage.input_tokens == 120
    assert usage.usage.output_tokens == 13


def test_openai_dispatches_tools_off_the_loop_thread():
    """Regression: the provider must dispatch tools OFF the asyncio loop thread, so a
    tool's sync ORM never trips Django's @async_unsafe guard on a reconnect. A tool
    that records its thread proves dispatch was offloaded; if it ran inline on the
    loop thread (the pre-fix behavior) the two thread ids match and this fails.
    """
    import threading

    from apps.ai.tools import Toolset, ToolSpec

    sink: dict = {}

    def _quote(ticker, **_):
        sink["tool_thread"] = threading.get_ident()
        return {"ticker": ticker, "last": 200}

    real_toolset = Toolset()
    real_toolset.register(
        ToolSpec(name="get_quote", description="q", input_schema={"type": "object"}, fn=_quote)
    )
    streams = [_FakeToolCallStream(), _FakeTextStream()]
    fake = MagicMock()

    async def fake_create(**_kwargs):
        return streams.pop(0)

    fake.chat.completions.create = fake_create
    loop: dict = {}

    async def go():
        loop["thread"] = threading.get_ident()
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="You help.",
            messages=[ChatMessage(role="user", content="quote AAPL")],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "get_quote", "description": "", "parameters": {}},
                }
            ],
        )
        return [evt async for evt in provider.run(req)]

    with (
        patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake),
        patch("apps.ai.providers.openai._resolve_toolset", return_value=real_toolset),
    ):
        events = asyncio.run(go())

    result_evt = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result_evt.ok is True
    assert sink["tool_thread"] != loop["thread"]  # dispatched off the loop thread


@pytest.mark.asyncio
async def test_openai_malformed_tool_args_degrades():
    """Invalid JSON arguments => error tool result, no toolset.run call, run still completes."""

    class _BadArgsStream:
        def __aiter__(self):
            async def gen():
                c = MagicMock()
                ch = MagicMock()
                ch.delta.content = None
                tc = MagicMock()
                tc.index = 0
                tc.id = "call_x"
                tc.function.name = "get_quote"
                tc.function.arguments = "{not json"
                ch.delta.tool_calls = [tc]
                ch.finish_reason = "tool_calls"
                c.choices = [ch]
                c.usage = MagicMock(
                    prompt_tokens=1,
                    completion_tokens=1,
                    prompt_tokens_details=MagicMock(cached_tokens=0),
                )
                yield c

            return gen()

    streams = [_BadArgsStream(), _FakeTextStream()]
    captured_calls = []
    fake = MagicMock()

    async def fake_create(**kwargs):
        captured_calls.append(kwargs)
        return streams.pop(0)

    fake.chat.completions.create = fake_create
    fake_toolset = MagicMock()

    with (
        patch("apps.ai.providers.openai.AsyncOpenAI", return_value=fake),
        patch("apps.ai.providers.openai._resolve_toolset", return_value=fake_toolset),
    ):
        provider = OpenAIProvider(api_key="sk-test")
        req = RunRequest(
            model="gpt-5",
            system="x",
            messages=[ChatMessage(role="user", content="q")],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "get_quote", "description": "", "parameters": {}},
                }
            ],
        )
        events = [evt async for evt in provider.run(req)]

    fake_toolset.run.assert_not_called()
    res_evt = next(e for e in events if isinstance(e, ToolResultEvent))
    assert res_evt.ok is False
    assert "json" in res_evt.error.lower()
    assert any(isinstance(e, DoneEvent) for e in events)
    assert len(captured_calls) == 2  # loop advanced to round 2 after the error result
