from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.mark.django_db
def test_compare_enqueues_one_task_per_branch(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")

    with patch("apps.threads.views.run_ai_on_message.delay") as enqueue:
        resp = api.post(
            f"/api/threads/{t.id}/compare/",
            {
                "text": "what about NVDA?",
                "branches": [
                    {"provider": "claude", "model": "claude-sonnet-4-6"},
                    {"provider": "openai", "model": "gpt-5-mini"},
                ],
            },
            format="json",
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "user_message_id" in body
    assert len(body["branches"]) == 2
    assert enqueue.call_count == 2
    for call in enqueue.call_args_list:
        assert call.kwargs["parent_message_id"] == body["user_message_id"]

    assert Message.objects.filter(thread=t, role="user").count() == 1


@pytest.mark.django_db
def test_compare_rejects_empty_branches(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    r = api.post(
        f"/api/threads/{t.id}/compare/",
        {"text": "hi", "branches": []},
        format="json",
    )
    assert r.status_code == 400
