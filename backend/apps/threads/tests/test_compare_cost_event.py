from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun, Message, Thread


@pytest.mark.django_db
def test_run_emits_cost_event_after_done(monkeypatch) -> None:
    # ProviderConfig is needed for provider resolution and ProviderConfig.objects.get().
    ProviderConfig.objects.create(  # type: ignore[misc]
        provider="claude",
        api_key="sk-ant-test",
        default_model="claude-3-5-haiku-20241022",
        enabled=True,
    )
    thread = Thread.objects.create(kind="consult", title="t")
    user_msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": "hi"},
        status="done",
    )

    events: list[dict] = []

    def fake_broadcast(_tid: int, payload: dict) -> None:
        events.append(payload)

    monkeypatch.setattr("apps.threads.tasks._broadcast", fake_broadcast)

    # Fake the provider drive loop so the task reaches the cost-emit branch.
    # Signature matches _build_stream_runner(buffer, usage_dict, err_container, provider, req, thread_id, assistant_id).
    # The extra args (provider, req, thread_id, assistant_id) are ignored by the fake.
    def fake_drive_factory(buffer_ref, usage_ref, err_ref, *_args):
        async def drive():
            buffer_ref.append("hello")
            usage_ref["input_tokens"] = 1000
            usage_ref["output_tokens"] = 100
            usage_ref["cached_tokens"] = 500

        return drive

    with (
        patch("apps.threads.tasks.cost_usd_for", return_value=Decimal("0.0123")),
        patch("apps.threads.tasks._build_stream_runner", side_effect=fake_drive_factory),
    ):
        from apps.threads.tasks import run_ai_on_message

        run_ai_on_message(
            thread_id=thread.id,
            user_message_id=user_msg.id,
            parent_message_id=user_msg.id,
        )

    cost_events = [e for e in events if e.get("event") == "cost"]
    assert len(cost_events) == 1
    ev = cost_events[0]
    assert ev["cost_usd"] == "0.0123"
    assert ev["tokens_in"] == 1000
    assert ev["tokens_out"] == 100
    assert ev["tokens_cached"] == 500
    assert ev["parent_message_id"] == user_msg.id
    assert "message_id" in ev
    assert "duration_ms" in ev

    ai_run = AIRun.objects.get()
    assert ai_run.cost_usd == Decimal("0.0123")
