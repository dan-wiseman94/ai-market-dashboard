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


def test_claude_count_cache_keys_are_hashes_not_text() -> None:
    """The LRU must key on (sha256(text), model) — caching the raw strings pins
    up-to-150k-token snapshot payloads in long-lived worker/web processes."""
    from apps.ai import token_counter

    token_counter._COUNT_CACHE.clear()
    big_text = "payload " * 20_000
    try:
        with patch.object(token_counter, "_claude_count_tokens_api", return_value=123) as api:
            n1 = token_counter._claude_count_tokens(big_text, "claude-opus-4-8")
            n2 = token_counter._claude_count_tokens(big_text, "claude-opus-4-8")
        assert n1 == n2 == 123
        api.assert_called_once()  # the second call is a cache hit, no network
        for (digest, model), count in token_counter._COUNT_CACHE.items():
            assert len(digest) == 64  # sha256 hex, not the payload text
            assert model == "claude-opus-4-8"
            assert count == 123
    finally:
        token_counter._COUNT_CACHE.clear()


def test_claude_count_cache_is_bounded() -> None:
    from apps.ai import token_counter

    token_counter._COUNT_CACHE.clear()
    try:
        with patch.object(token_counter, "_claude_count_tokens_api", return_value=1):
            for i in range(token_counter._COUNT_CACHE_MAX + 10):
                token_counter._claude_count_tokens(f"text-{i}", "m")
        assert len(token_counter._COUNT_CACHE) == token_counter._COUNT_CACHE_MAX
    finally:
        token_counter._COUNT_CACHE.clear()
