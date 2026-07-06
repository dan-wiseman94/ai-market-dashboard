"""An errored stream must bill the usage that already accrued.

Completed tool rounds are genuinely charged by the provider (each round
re-sends the whole conversation), so a run that fails on a later round must
still count its partial spend against the daily/monthly caps — a $0 failed
AIRun systematically under-counts exactly the longest, most expensive runs.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_failed_run_records_partial_usage_and_cost():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import ErrorEvent, TextDelta, TokenUsage, UsageEvent

    async def fake_stream(self, req):
        # Round 1 completed (cumulative usage emitted), then round 2 errored.
        yield TextDelta(text="partial answer")
        yield UsageEvent(usage=TokenUsage(input_tokens=1000, output_tokens=200))
        yield ErrorEvent(message="Anthropic overloaded on round 2")

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is False
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert assistant.status == "failed"

    run = AIRun.objects.get(message=assistant)
    assert run.status == "failed"
    assert run.input_tokens == 1000
    assert run.output_tokens == 200
    assert run.cost_usd > 0  # partial spend counts against the caps


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_failed_run_with_no_usage_bills_zero():
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-test")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import ErrorEvent

    async def fake_stream(self, req):
        yield ErrorEvent(message="401 unauthorized")

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_stream):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is False
    assistant = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    run = AIRun.objects.get(message=assistant)
    assert run.status == "failed"
    assert run.input_tokens == 0
    assert not run.cost_usd
