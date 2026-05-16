"""The harness itself works: mocks produce expected deterministic outputs."""

from __future__ import annotations

import asyncio
import os


def test_mock_mode_flag() -> None:
    os.environ["MOCK_EXTERNAL"] = "true"
    from apps.core.mocks import is_mock_mode

    assert is_mock_mode() is True
    del os.environ["MOCK_EXTERNAL"]


def test_mock_mode_flag_off() -> None:
    os.environ.pop("MOCK_EXTERNAL", None)
    from apps.core.mocks import is_mock_mode

    assert is_mock_mode() is False


def test_mocked_ai_provider_yields_canned_stream(monkeypatch) -> None:
    monkeypatch.setenv("MOCK_EXTERNAL", "true")
    from apps.ai.providers.claude import ClaudeProvider
    from apps.ai.types import ChatMessage, RunRequest

    provider = ClaudeProvider(api_key="test-key-not-used-in-mock-mode")
    req = RunRequest(
        model="claude-sonnet-4-6",
        system="",
        messages=[ChatMessage(role="user", content="hi")],
    )

    async def collect():
        return [ev async for ev in provider.run(req)]

    events = asyncio.run(collect())
    assert any(getattr(e, "type", None) == "text_delta" for e in events)
    assert any(getattr(e, "type", None) == "done" for e in events)
    text = "".join(getattr(e, "text", "") for e in events)
    assert "Mocked" in text
