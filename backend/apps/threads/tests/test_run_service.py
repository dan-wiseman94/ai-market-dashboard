"""The service-layer run entrypoint (apps.threads.services.run.run_ai): a plain
synchronous callable with the same behavior as the Celery task, whose return
carries the assistant message id so callers never scrape threads by ordering."""

from unittest.mock import MagicMock, patch

import pytest

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread
from apps.threads.services.run import run_ai


def _noop_runner(*a, **k):
    async def drive():
        return None

    return drive


@pytest.mark.django_db
def test_run_ai_returns_the_assistant_message_id_on_success():
    ProviderConfig.objects.create(provider="claude", api_key="sk")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", _noop_runner),
    ):
        out = run_ai(thread_id=t.id, user_message_id=u.id)

    a = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert out == {"ok": True, "message_id": a.id}
    assert a.status == "done"


@pytest.mark.django_db
def test_run_ai_failure_also_carries_the_failed_message_id():
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})

    with patch(
        "apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")
    ):
        out = run_ai(thread_id=t.id, user_message_id=u.id)  # no ProviderConfig row

    failed = Message.objects.filter(thread=t, role="assistant", status="failed").latest(
        "created_at"
    )
    assert out == {"ok": False, "error": "no_key", "message_id": failed.id}
