from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_uses_openai_when_profile_defaults_to_openai():
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini",
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
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-x")
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini",
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
            thread_id=t.id, user_message_id=u.id,
            override={"provider": "claude", "model": "claude-opus-4-7"},
        ).get(timeout=5)

    assert result["ok"] is True
    assert calls["provider_name"] == "claude"
    assert calls["model"] == "claude-opus-4-7"
