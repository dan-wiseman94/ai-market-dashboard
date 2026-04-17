from unittest.mock import MagicMock, patch

import pytest

from apps.ai.providers.claude import ClaudeProvider
from apps.ai.types import ChatMessage, RunRequest, TextDelta, UsageEvent, DoneEvent


class _FakeStream:
    """Mimics anthropic's async streaming context manager."""

    def __init__(self, text_chunks, usage):
        self._text_chunks = text_chunks
        self._usage = usage

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    def __aiter__(self):
        async def gen():
            for c in self._text_chunks:
                yield MagicMock(type="text", text=c)
            yield MagicMock(type="message_stop")
        return gen()

    async def get_final_message(self):
        msg = MagicMock()
        msg.usage.input_tokens = self._usage["input"]
        msg.usage.output_tokens = self._usage["output"]
        msg.usage.cache_read_input_tokens = self._usage.get("cached", 0)
        msg.usage.cache_creation_input_tokens = 0
        return msg


@pytest.mark.asyncio
async def test_claude_streams_text_and_usage():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=_FakeStream(
        ["Hello", " ", "world"], {"input": 100, "output": 50, "cached": 10},
    ))

    with patch("apps.ai.providers.claude.AsyncAnthropic", return_value=fake_client):
        provider = ClaudeProvider(api_key="sk-ant-test")
        req = RunRequest(
            model="claude-sonnet-4-6",
            system="You are helpful.",
            messages=[ChatMessage(role="user", content="hi")],
        )
        events = []
        async for evt in provider.run(req):
            events.append(evt)

    text_parts = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(text_parts) == "Hello world"

    usage = next(e for e in events if isinstance(e, UsageEvent))
    assert usage.usage.input_tokens == 100
    assert usage.usage.output_tokens == 50
    assert usage.usage.cached_tokens == 10

    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_claude_sends_cache_control_when_enabled():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=_FakeStream(["hi"], {"input": 1, "output": 1}))

    with patch("apps.ai.providers.claude.AsyncAnthropic", return_value=fake_client):
        provider = ClaudeProvider(api_key="sk-ant-test")
        req = RunRequest(
            model="claude-sonnet-4-6",
            system="LONG STYLE PROMPT",
            messages=[ChatMessage(role="user", content="hi")],
            cache_system=True,
        )
        async for _ in provider.run(req):
            pass

    kwargs = fake_client.messages.stream.call_args.kwargs
    sys_blocks = kwargs["system"]
    assert isinstance(sys_blocks, list)
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
