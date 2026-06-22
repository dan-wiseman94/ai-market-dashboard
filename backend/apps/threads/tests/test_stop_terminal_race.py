"""A stop that lands during the run must not be un-cancelled or billed.

The worker's terminal write and the stop endpoint both compare-and-set on
status='streaming', so whichever flips status first wins. Here a concurrent
cancel lands mid-stream; the run must finish 'failed/cancelled' with a
zero-cost AIRun, never flipped back to 'done'.
"""

from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread
from apps.threads.tasks import run_ai_on_message


@pytest.mark.django_db(transaction=True)  # real commits: the mid-stream flip must be visible
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_concurrent_cancel_is_not_un_cancelled_or_billed():
    ProviderConfig.objects.create(provider="openai", api_key="sk-oai-x")  # type: ignore[misc]
    p = TradingProfile.objects.create(
        name="P", style="x", default_provider="openai", default_model="gpt-5-mini"
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    from apps.ai.types import DoneEvent, TextDelta, TokenUsage, UsageEvent

    async def fake_run(self, req):
        yield TextDelta(text="partial")
        # A stop lands mid-stream: CAS-cancel the streaming assistant message.
        await sync_to_async(
            lambda: Message.objects.filter(
                thread_id=t.id, role="assistant", status="streaming"
            ).update(status="failed", error="cancelled")
        )()
        yield UsageEvent(usage=TokenUsage(input_tokens=10, output_tokens=5))
        yield DoneEvent()

    with patch("apps.ai.providers.openai.OpenAIProvider.run", fake_run):
        result = run_ai_on_message.delay(thread_id=t.id, user_message_id=u.id).get(timeout=5)

    assert result["ok"] is False
    assert result["error"] == "cancelled"

    asst = Message.objects.filter(thread=t, role="assistant").latest("id")
    assert asst.status == "failed"  # NOT un-cancelled back to "done"
    assert asst.error == "cancelled"

    run = AIRun.objects.get(message=asst)
    assert run.status == "failed"
    assert not run.cost_usd  # 0/None — a cancelled run is never billed
