from unittest.mock import MagicMock, patch

import pytest

from apps.ai.providers.openai import OpenAIProvider
from apps.ai.types import ChatMessage, DoneEvent, RunRequest, TextDelta, UsageEvent


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
