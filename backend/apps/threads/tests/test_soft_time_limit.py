"""Celery's soft time limit (config.celery task_soft_time_limit — "catchable
cleanup") must actually be caught: a SoftTimeLimitExceeded landing mid-run has to
finalize the assistant Message (failed + error broadcast + partial usage billed)
and re-raise, instead of leaving it stuck "streaming" until the hard-limit
SIGKILL (acks_late=False means nothing would ever finalize it)."""

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread
from apps.threads.tasks import _run_ai_on_message


def _setup():
    ProviderConfig.objects.create(provider="claude", api_key="sk")  # type: ignore[misc]
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    u = Message.objects.create(thread=t, role="user", content={"text": "hi"})
    return t, u


@pytest.mark.django_db
def test_soft_time_limit_fails_message_bills_partial_and_reraises():
    t, u = _setup()

    def limit_runner(buffer, counts, *a, **k):
        async def drive():
            buffer.append("partial ")
            counts["output_tokens"] = 7
            raise SoftTimeLimitExceeded()

        return drive

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", limit_runner),
        patch("apps.threads.tasks._broadcast") as bc,
        pytest.raises(SoftTimeLimitExceeded),
    ):
        _run_ai_on_message(thread_id=t.id, user_message_id=u.id)

    a = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert a.status == "failed"
    assert "time limit" in a.error
    assert a.content["text"] == "partial "  # the partial stream is preserved
    run = AIRun.objects.get(message=a)
    assert run.status == "failed"
    assert run.output_tokens == 7  # partial usage still billed against the caps
    events = [c.args[1]["event"] for c in bc.call_args_list]
    assert "error" in events  # the UI was unblocked


@pytest.mark.django_db
def test_soft_time_limit_never_clobbers_an_already_finalized_message():
    """CAS guard: if the message already left "streaming" (stop endpoint won the
    race), the soft-limit cleanup must not overwrite it or double-create an AIRun."""
    t, u = _setup()

    def limit_runner(buffer, *a, **k):
        async def drive():
            raise SoftTimeLimitExceeded()

        return drive

    def flip_to_cancelled(message_id):
        Message.objects.filter(id=message_id).update(status="failed", error="cancelled")

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("claude", "claude-x")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", limit_runner),
        patch("apps.threads.tasks.clear_stop", side_effect=flip_to_cancelled),
        patch("apps.threads.tasks._broadcast"),
        pytest.raises(SoftTimeLimitExceeded),
    ):
        _run_ai_on_message(thread_id=t.id, user_message_id=u.id)

    a = Message.objects.filter(thread=t, role="assistant").latest("created_at")
    assert a.error == "cancelled"  # untouched
    assert not AIRun.objects.filter(message=a).exists()
