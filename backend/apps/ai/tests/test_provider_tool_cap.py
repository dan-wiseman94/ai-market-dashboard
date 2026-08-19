"""max_tool_iterations bounds the agentic tool loop in both providers.

The stubbed streams ALWAYS ask for another tool round, so without the cap the
loop would never terminate — the assertion is that exactly N rounds happen.
"""

from typing import ClassVar

import pytest

from apps.ai.providers.claude import ClaudeProvider
from apps.ai.providers.openai import OpenAIProvider
from apps.ai.types import RunRequest, ToolCallEvent


class _Block:
    type = "tool_use"
    id = "tu_1"
    name = "get_quote"
    input: ClassVar = {"ticker": "NVDA"}


class _Usage:
    input_tokens = 1
    output_tokens = 1
    cache_read_input_tokens = 0


class _Final:
    stop_reason = "tool_use"  # model ALWAYS wants another tool round
    usage = _Usage()
    content: ClassVar = [_Block()]


class _FakeClaudeStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def _gen():
            if False:  # no text events needed for this test
                yield None

        return _gen()

    async def get_final_message(self):
        return _Final()


class _FakeToolset:
    def run(self, name, inp):
        return {"ok": True, "result": "42"}


@pytest.mark.asyncio
async def test_claude_caps_tool_rounds(monkeypatch):
    provider = ClaudeProvider(api_key="k")
    monkeypatch.setattr(provider._client.messages, "stream", lambda **kw: _FakeClaudeStream())
    monkeypatch.setattr("apps.ai.providers.claude._resolve_toolset", lambda: _FakeToolset())

    req = RunRequest(
        model="claude-x",
        system="s",
        messages=[],
        tools=[{"name": "get_quote", "input_schema": {"type": "object"}}],
        max_tool_iterations=2,
    )
    tool_calls = [e async for e in provider.run(req) if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 2  # bounded: 2 rounds, then a tool-less concluding turn


class _FN:
    name = "get_quote"
    arguments = '{"ticker":"NVDA"}'


class _TC:
    index = 0
    id = "tc1"
    function = _FN()


class _Delta:
    content = None
    tool_calls: ClassVar = [_TC()]


class _Choice:
    delta = _Delta()
    finish_reason = "tool_calls"  # always wants another round


class _Chunk:
    choices: ClassVar = [_Choice()]
    usage = None


async def _fake_create(**kw):
    async def gen():
        yield _Chunk()

    return gen()


@pytest.mark.asyncio
async def test_openai_caps_tool_rounds(monkeypatch):
    provider = OpenAIProvider(api_key="k")
    monkeypatch.setattr(provider._client.chat.completions, "create", _fake_create)
    monkeypatch.setattr("apps.ai.providers.openai._resolve_toolset", lambda: _FakeToolset())

    req = RunRequest(
        model="gpt-x",
        system="s",
        messages=[],
        tools=[{"type": "function", "function": {"name": "get_quote"}}],
        max_tool_iterations=2,
    )
    tool_calls = [e async for e in provider.run(req) if isinstance(e, ToolCallEvent)]
    assert len(tool_calls) == 2
