"""Cross-provider failover: when the PRIMARY provider errors before
emitting any token, retry once on a configured secondary provider.

Opt-in (AI_FAILOVER_ENABLED, default off). Never retries once a token has
streamed (that would duplicate/garble output) — that's the load-bearing guard.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread
from apps.threads.tasks import _failover_target, _run_ai_on_message


def _thread_with_user(provider: str = "claude", model: str = "claude-sonnet-4-6"):
    p = TradingProfile.objects.create(
        name="p", style="s", default_provider=provider, default_model=model
    )
    t = Thread.objects.create(kind="chat", profile=p)
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"}, status="done")
    return t, u


async def _err_before_token(self, req):
    from apps.ai.types import ErrorEvent

    yield ErrorEvent(message="primary 503 before any token")


async def _ok_secondary(self, req):
    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    yield TextDelta(text="from secondary")
    yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5, cached_tokens=0))
    yield DoneEvent()


# --------------------------------------------------------------------------- #
# _failover_target unit
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_failover_target_none_when_disabled():
    ProviderConfig.objects.create(provider="openai", api_key="sk", default_model="gpt-5")
    with override_settings(AI_FAILOVER_ENABLED=False, AI_FAILOVER_PROVIDER="openai"):
        assert _failover_target("claude") is None


@pytest.mark.django_db
def test_failover_target_resolves_enabled_secondary():
    ProviderConfig.objects.create(
        provider="openai", api_key="sk", default_model="gpt-5", enabled=True
    )
    with override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER="openai"):
        out = _failover_target("claude")
    assert out is not None
    name, model, _cfg = out
    assert name == "openai" and model == "gpt-5"


@pytest.mark.django_db
def test_failover_target_none_when_same_as_primary():
    ProviderConfig.objects.create(provider="claude", api_key="sk", default_model="claude-x")
    with override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER="claude"):
        assert _failover_target("claude") is None


@pytest.mark.django_db
def test_failover_target_none_when_secondary_has_no_model():
    ProviderConfig.objects.create(provider="openai", api_key="sk", default_model="", enabled=True)
    with override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER="openai"):
        assert _failover_target("claude") is None


@pytest.mark.django_db
def test_failover_target_none_when_secondary_disabled():
    ProviderConfig.objects.create(
        provider="openai", api_key="sk", default_model="gpt-5", enabled=False
    )
    with override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER="openai"):
        assert _failover_target("claude") is None


# --------------------------------------------------------------------------- #
# Integration
# --------------------------------------------------------------------------- #
@pytest.mark.django_db
def test_failover_retries_secondary_when_primary_fails_before_token():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant")
    ProviderConfig.objects.create(
        provider="openai", api_key="sk-oai", default_model="gpt-5", enabled=True
    )
    t, u = _thread_with_user("claude", "claude-sonnet-4-6")
    with (
        override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER="openai"),
        patch("apps.ai.providers.claude.ClaudeProvider.run", _err_before_token),
        patch("apps.ai.providers.openai.OpenAIProvider.run", _ok_secondary),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)
    assert out["ok"] is True
    a = Message.objects.get(thread=t, role="assistant")
    assert a.status == "done"
    assert a.content["text"] == "from secondary"
    run = AIRun.objects.get(message=a)
    assert run.provider == "openai" and run.model == "gpt-5"


@pytest.mark.django_db
def test_no_failover_when_disabled_primary_error_is_final():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant")
    ProviderConfig.objects.create(
        provider="openai", api_key="sk-oai", default_model="gpt-5", enabled=True
    )
    t, u = _thread_with_user("claude")
    with (
        override_settings(AI_FAILOVER_ENABLED=False),
        patch("apps.ai.providers.claude.ClaudeProvider.run", _err_before_token),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)
    assert out["ok"] is False
    a = Message.objects.get(thread=t, role="assistant")
    assert a.status == "failed"
    assert AIRun.objects.get(message=a).provider == "claude"


@pytest.mark.django_db
def test_no_failover_when_primary_fails_midstream():
    """A token already streamed -> no retry (would duplicate output); the partial
    primary text and provider are preserved."""

    async def _midfail(self, req):
        from apps.ai.types import ErrorEvent, TextDelta

        yield TextDelta(text="partial")
        yield ErrorEvent(message="died mid-stream")

    ProviderConfig.objects.create(provider="claude", api_key="sk-ant")
    ProviderConfig.objects.create(
        provider="openai", api_key="sk-oai", default_model="gpt-5", enabled=True
    )
    t, u = _thread_with_user("claude")
    with (
        override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER="openai"),
        patch("apps.ai.providers.claude.ClaudeProvider.run", _midfail),
        patch("apps.ai.providers.openai.OpenAIProvider.run", _ok_secondary),
    ):
        out = _run_ai_on_message(thread_id=t.id, user_message_id=u.id)
    assert out["ok"] is False
    a = Message.objects.get(thread=t, role="assistant")
    assert a.status == "failed"
    assert a.content["text"] == "partial"
    assert AIRun.objects.get(message=a).provider == "claude"
