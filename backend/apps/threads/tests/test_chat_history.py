from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_chat_mode_passes_full_history_to_provider():
    """Multi-turn chat: the second send should include the first exchange."""
    ProviderConfig.objects.create(provider="claude", api_key="sk-ant-x")  # type: ignore[misc]
    p = TradingProfile.objects.create(
        name="P",
        style="You trade.",
        default_provider="claude",
        default_model="claude-sonnet-4-6",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")

    Message.objects.create(thread=t, role="user", content={"text": "first question"}, status="done")
    Message.objects.create(
        thread=t, role="assistant", content={"text": "first answer"}, status="done"
    )

    from apps.ai.types import DoneEvent, TextDelta
    from apps.threads.tasks import run_ai_on_message

    captured = {}

    async def fake_run(self, req):
        captured["messages"] = [(m.role, m.content) for m in req.messages]
        yield TextDelta(text="second answer")
        yield DoneEvent()

    new_user = Message.objects.create(
        thread=t,
        role="user",
        content={"text": "follow-up?"},
        status="done",
    )

    with patch("apps.ai.providers.claude.ClaudeProvider.run", fake_run):
        run_ai_on_message.delay(thread_id=t.id, user_message_id=new_user.id).get(timeout=5)

    roles = [role for role, _ in captured["messages"]]
    assert roles == ["user", "assistant", "user"]
    contents = [content for _, content in captured["messages"]]
    assert contents == ["first question", "first answer", "follow-up?"]
