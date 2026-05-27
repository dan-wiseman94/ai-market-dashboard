from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_run_ai_appends_assistant_message_and_airun():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="You trade.")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    user_msg = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    async def fake_stream(self, req):
        yield TextDelta(text="Hello")
        yield TextDelta(text=" world")
        yield UsageEvent(usage=TokenUsage(input_tokens=100, output_tokens=50, cached_tokens=0))
        yield DoneEvent()

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_stream):
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
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import ErrorEvent

    async def fake_stream(self, req):
        yield ErrorEvent(message="Anthropic rate limit")

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is False
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert assistant.status == "failed"
    assert "rate limit" in assistant.error


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_run_ai_blocked_when_provider_disabled():
    # Profile pins provider+model, which resolve_provider_and_model returns without
    # consulting `enabled`; the task must still refuse a disabled provider.
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test", enabled=False)  # type: ignore[misc]
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="claude", default_model="claude-sonnet-4-6"
    )
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    with patch("apps.threads.tasks._broadcast"):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result == {"ok": False, "error": "provider_disabled"}
    assert not Message.objects.filter(thread=t, role="assistant", status="done").exists()
    failed = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert "disabled" in failed.error


@pytest.mark.django_db
def test_emit_capability_warning_writes_system_message():
    from apps.threads.models import Message, Thread
    from apps.threads.tasks import _emit_capability_warning

    thread = Thread.objects.create(kind="consult")
    with patch("apps.threads.tasks._broadcast") as bc:
        wrote = _emit_capability_warning(
            thread_id=thread.id, features=["extended thinking"], provider_name="openai"
        )
    assert wrote is True
    msg = Message.objects.filter(thread=thread, role="system").latest("created_at")
    assert "extended thinking" in msg.content["text"]
    assert "openai" in msg.content["text"]
    assert bc.call_args[0][1]["event"] == "warning"


@pytest.mark.django_db
def test_emit_capability_warning_dedupes():
    from apps.threads.models import Message, Thread
    from apps.threads.tasks import _emit_capability_warning

    thread = Thread.objects.create(kind="consult")
    with patch("apps.threads.tasks._broadcast"):
        first = _emit_capability_warning(
            thread_id=thread.id, features=["memory"], provider_name="local"
        )
        second = _emit_capability_warning(
            thread_id=thread.id, features=["memory"], provider_name="local"
        )
    assert first is True
    assert second is False
    assert Message.objects.filter(thread=thread, role="system").count() == 1
