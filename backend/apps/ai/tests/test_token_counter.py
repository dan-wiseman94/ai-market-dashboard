"""Token estimator must route by provider: Anthropic count_tokens for Claude,
tiktoken for OpenAI/local. Must never raise on empty or non-ASCII strings.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.ai.token_counter import estimate_tokens


def test_estimate_empty_string_returns_zero() -> None:
    assert estimate_tokens("", provider="claude", model="claude-opus-4-8") == 0
    assert estimate_tokens("", provider="openai", model="gpt-5") == 0


def test_estimate_openai_uses_tiktoken() -> None:
    n = estimate_tokens("hello world", provider="openai", model="gpt-5")
    assert 1 <= n <= 4


def test_estimate_local_uses_tiktoken() -> None:
    n = estimate_tokens("hello world", provider="local", model="whatever")
    assert 1 <= n <= 4


def test_estimate_claude_calls_sdk_count_tokens() -> None:
    with patch("apps.ai.token_counter._claude_count_tokens", return_value=42) as m:
        n = estimate_tokens("any text", provider="claude", model="claude-opus-4-8")
    assert n == 42
    m.assert_called_once()


def test_estimate_unicode_no_crash() -> None:
    assert estimate_tokens("🔥日本語", provider="openai", model="gpt-5") > 0
    with patch("apps.ai.token_counter._claude_count_tokens", return_value=7):
        assert estimate_tokens("🔥日本語", provider="claude", model="claude-opus-4-8") == 7


def test_unknown_provider_falls_back_to_tiktoken() -> None:
    n = estimate_tokens("hello", provider="ollama", model="llama3")
    assert n >= 1


@pytest.mark.django_db
def test_claude_count_falls_back_to_tiktoken_when_key_undecryptable() -> None:
    """An undecryptable Claude key (key/salt rotation) must degrade to the tiktoken
    estimate rather than raising InvalidToken mid-run."""
    from django.db import connection

    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude")
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet", "claude"],
        )
    n = estimate_tokens("hello world", provider="claude", model="claude-opus-4-8")
    assert n >= 1
