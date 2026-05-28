from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread
from apps.threads.tasks import _build_request, run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_uses_openai_when_profile_defaults_to_openai():
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")  # type: ignore[misc]
    p = TradingProfile.objects.create(
        name="P",
        style="x",
        default_provider="openai",
        default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    calls = {}

    async def fake_run(self, req):
        calls["provider_name"] = self.name
        calls["model"] = req.model
        yield TextDelta(text="out")
        yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5))
        yield DoneEvent()

    with patch("apps.ai.providers.openai.OpenAIProvider.run", fake_run):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is True
    assert calls["provider_name"] == "openai"
    assert calls["model"] == "gpt-5-mini"


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_override_routes_to_claude():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-x")  # type: ignore[misc]
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")  # type: ignore[misc]
    p = TradingProfile.objects.create(
        name="P",
        style="x",
        default_provider="openai",
        default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta

    calls = {}

    async def fake_run(self, req):
        calls["provider_name"] = self.name
        calls["model"] = req.model
        yield TextDelta(text="hi")
        yield DoneEvent()

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_run):
        result = run_ai_on_message.delay(
            thread_id=t.id,
            user_message_id=u.id,
            override={"provider": "claude", "model": "claude-opus-4-8"},
        ).get(timeout=5)

    assert result["ok"] is True
    assert calls["provider_name"] == "claude"
    assert calls["model"] == "claude-opus-4-8"


@pytest.fixture
def tools_thread(db):
    profile = TradingProfile.objects.create(name="Tooler", style="be helpful", enable_tools=True)
    thread = Thread.objects.create(kind="consult", profile=profile)
    msg = Message.objects.create(
        thread=thread, role="user", content={"text": "quote AAPL"}, status="done"
    )
    return thread, msg


@pytest.mark.django_db
def test_build_request_openai_tools_when_supported(tools_thread):
    thread, msg = tools_thread
    fake_tools = [{"type": "function", "function": {"name": "get_quote"}}]
    with patch("apps.ai.tools.registry.default_toolset") as ts:
        ts.return_value.openai_tools.return_value = fake_tools
        req = _build_request(thread, msg, provider_name="openai", supports_tools=True)
    assert req.tools == fake_tools


@pytest.mark.django_db
def test_build_request_openai_no_tools_when_unsupported(tools_thread):
    thread, msg = tools_thread
    req = _build_request(thread, msg, provider_name="local", supports_tools=False)
    assert req.tools == []


@pytest.mark.django_db
def test_build_request_claude_uses_anthropic_tools(tools_thread):
    thread, msg = tools_thread
    fake_tools = [{"name": "get_quote", "description": "", "input_schema": {}}]
    with patch("apps.ai.tools.registry.default_toolset") as ts:
        ts.return_value.anthropic_tools.return_value = fake_tools
        req = _build_request(thread, msg, provider_name="claude", supports_tools=False)
    assert req.tools == fake_tools
