from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Thread, Message
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_run_ai_appends_assistant_message_and_airun():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")
    p = TradingProfile.objects.create(name="P", style="You trade.")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    user_msg = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    async def fake_stream(self, req):
        yield TextDelta(text="Hello")
        yield TextDelta(text=" world")
        yield UsageEvent(usage=TokenUsage(input_tokens=100, output_tokens=50, cached_tokens=0))
        yield DoneEvent()

    with patch("apps.threads.tasks.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=user_msg.id).get(timeout=5)

    assert result["ok"] is True
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert "Hello world" in assistant.content.get("text", "")
    assert assistant.status == "done"
    run = assistant.ai_run
    assert run.provider == "claude"
    assert run.input_tokens == 100
    assert run.output_tokens == 50
    assert run.cost_usd > 0


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_run_ai_marks_failed_on_error():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import ErrorEvent

    async def fake_stream(self, req):
        yield ErrorEvent(message="Anthropic rate limit")

    with patch("apps.threads.tasks.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is False
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert assistant.status == "failed"
    assert "rate limit" in assistant.error
