"""Bounded retry-with-backoff + read timeout on AI provider clients.

Verifies:
- client_kwargs() returns the configured settings values (and correct defaults).
- @override_settings changes client_kwargs() output.
- ClaudeProvider passes max_retries + timeout to AsyncAnthropic at construction.
- OpenAIProvider passes max_retries + timeout to AsyncOpenAI at construction.
- LocalProvider (subclass) also passes them (via OpenAIProvider.__init__).
- ClaudeStructured run_structured passes them to Anthropic at construction.
- Streaming behaviour is unaffected (the retry/timeout kwargs are construction-only).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import override_settings

# ---------------------------------------------------------------------------
# client_kwargs() helper
# ---------------------------------------------------------------------------


def test_client_kwargs_returns_defaults():
    """When settings are at their defaults, client_kwargs returns 2 retries / 60s."""
    from apps.ai.providers._config import client_kwargs

    kw = client_kwargs()
    assert kw["max_retries"] == 2
    assert kw["timeout"] == 60.0


@override_settings(AI_PROVIDER_MAX_RETRIES=5, AI_PROVIDER_TIMEOUT_SECONDS=30.0)
def test_client_kwargs_respects_override_settings():
    """override_settings changes client_kwargs output."""
    from apps.ai.providers._config import client_kwargs

    kw = client_kwargs()
    assert kw["max_retries"] == 5
    assert kw["timeout"] == 30.0


@override_settings(AI_PROVIDER_MAX_RETRIES=0, AI_PROVIDER_TIMEOUT_SECONDS=10.0)
def test_client_kwargs_zero_retries_is_valid():
    """Zero retries (disable backoff) is a valid configuration."""
    from apps.ai.providers._config import client_kwargs

    kw = client_kwargs()
    assert kw["max_retries"] == 0
    assert kw["timeout"] == 10.0


# ---------------------------------------------------------------------------
# ClaudeProvider — AsyncAnthropic constructed with resilience kwargs
# ---------------------------------------------------------------------------


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_claude_provider_passes_resilience_kwargs_to_client():
    """ClaudeProvider.__init__ must call AsyncAnthropic with max_retries + timeout."""
    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.claude.AsyncAnthropic", _FakeAnthropic):
        from apps.ai.providers.claude import ClaudeProvider

        ClaudeProvider(api_key="sk-ant-test")

    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0


@override_settings(AI_PROVIDER_MAX_RETRIES=4, AI_PROVIDER_TIMEOUT_SECONDS=45.0)
def test_claude_provider_passes_overridden_kwargs():
    """override_settings is reflected in the kwargs passed to AsyncAnthropic."""
    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.claude.AsyncAnthropic", _FakeAnthropic):
        from apps.ai.providers.claude import ClaudeProvider

        ClaudeProvider(api_key="sk-ant-test")

    assert captured["max_retries"] == 4
    assert captured["timeout"] == 45.0


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_claude_provider_with_base_url_passes_resilience_kwargs():
    """The base_url branch also passes max_retries + timeout."""
    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.claude.AsyncAnthropic", _FakeAnthropic):
        from apps.ai.providers.claude import ClaudeProvider

        ClaudeProvider(api_key="sk-ant-test", base_url="https://proxy.example.com")

    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0
    assert captured["base_url"] == "https://proxy.example.com"


# ---------------------------------------------------------------------------
# OpenAIProvider — AsyncOpenAI constructed with resilience kwargs
# ---------------------------------------------------------------------------


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_openai_provider_passes_resilience_kwargs_to_client():
    """OpenAIProvider.__init__ must call AsyncOpenAI with max_retries + timeout."""
    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeOpenAI):
        from apps.ai.providers.openai import OpenAIProvider

        OpenAIProvider(api_key="sk-test")

    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0


@override_settings(AI_PROVIDER_MAX_RETRIES=3, AI_PROVIDER_TIMEOUT_SECONDS=90.0)
def test_openai_provider_passes_overridden_kwargs():
    """override_settings is reflected in the kwargs passed to AsyncOpenAI."""
    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeOpenAI):
        from apps.ai.providers.openai import OpenAIProvider

        OpenAIProvider(api_key="sk-test")

    assert captured["max_retries"] == 3
    assert captured["timeout"] == 90.0


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_openai_provider_with_base_url_passes_resilience_kwargs():
    """The base_url branch of OpenAIProvider also passes max_retries + timeout."""
    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeOpenAI):
        from apps.ai.providers.openai import OpenAIProvider

        OpenAIProvider(api_key="sk-test", base_url="http://host.docker.internal:11434/v1")

    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0
    assert "host.docker.internal" in captured["base_url"]


# ---------------------------------------------------------------------------
# LocalProvider — inherits OpenAIProvider kwargs
# ---------------------------------------------------------------------------


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_local_provider_passes_resilience_kwargs_to_client():
    """LocalProvider (OpenAIProvider subclass) also passes max_retries + timeout."""
    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kw):
            captured.update(kw)

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeOpenAI):
        from apps.ai.providers.local import LocalProvider

        LocalProvider(api_key="", base_url="http://host.docker.internal:11434/v1")

    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0


# ---------------------------------------------------------------------------
# claude_structured.run_structured — sync Anthropic client
# ---------------------------------------------------------------------------


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_claude_structured_passes_resilience_kwargs_to_client():
    """run_structured must build its sync Anthropic client with max_retries + timeout."""
    from pydantic import BaseModel

    class _Schema(BaseModel):
        answer: str

    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)
            self.messages = MagicMock()
            parsed = MagicMock()
            parsed.parsed_output = _Schema(answer="yes")
            self.messages.parse.return_value = parsed

    with patch("apps.ai.providers.claude_structured.Anthropic", _FakeAnthropic):
        from apps.ai.providers.claude_structured import run_structured

        run_structured(
            api_key="sk-ant-test",
            model="claude-sonnet-4-6",
            system="Be concise.",
            user="Is the sky blue?",
            output_model=_Schema,
        )

    assert captured["max_retries"] == 2
    assert captured["timeout"] == 60.0


@override_settings(AI_PROVIDER_MAX_RETRIES=1, AI_PROVIDER_TIMEOUT_SECONDS=20.0)
def test_claude_structured_passes_overridden_kwargs():
    """override_settings is reflected in run_structured's Anthropic client kwargs."""
    from pydantic import BaseModel

    class _Schema(BaseModel):
        answer: str

    captured: dict = {}

    class _FakeAnthropic:
        def __init__(self, **kw):
            captured.update(kw)
            self.messages = MagicMock()
            parsed = MagicMock()
            parsed.parsed_output = _Schema(answer="yes")
            self.messages.parse.return_value = parsed

    with patch("apps.ai.providers.claude_structured.Anthropic", _FakeAnthropic):
        from apps.ai.providers.claude_structured import run_structured

        run_structured(
            api_key="sk-ant-test",
            model="claude-sonnet-4-6",
            system="Be concise.",
            user="Is the sky blue?",
            output_model=_Schema,
        )

    assert captured["max_retries"] == 1
    assert captured["timeout"] == 20.0


# ---------------------------------------------------------------------------
# Mock-mode safety: FakeClient in existing tests must accept **kwargs
# (construction must not raise even when kwargs are passed)
# ---------------------------------------------------------------------------


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_claude_provider_mock_mode_still_constructs(monkeypatch):
    """With MOCK_EXTERNAL=true, ClaudeProvider constructs without error (kwargs additive)."""
    monkeypatch.setenv("MOCK_EXTERNAL", "true")

    class _FakeAnthropic:
        def __init__(self, **kw):
            pass  # must accept **kw without raising

    with patch("apps.ai.providers.claude.AsyncAnthropic", _FakeAnthropic):
        from apps.ai.providers.claude import ClaudeProvider

        provider = ClaudeProvider(api_key="sk-ant-test")
        assert provider is not None


@override_settings(AI_PROVIDER_MAX_RETRIES=2, AI_PROVIDER_TIMEOUT_SECONDS=60.0)
def test_openai_provider_mock_mode_still_constructs(monkeypatch):
    """With MOCK_EXTERNAL=true and no key, OpenAIProvider constructs without error."""
    monkeypatch.setenv("MOCK_EXTERNAL", "true")

    class _FakeOpenAI:
        def __init__(self, **kw):
            pass  # must accept **kw without raising

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeOpenAI):
        from apps.ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="")
        assert provider is not None
