from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Message, Thread


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_consult_thread(api):
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    resp = api.post(
        "/api/threads/",
        {
            "kind": "consult",
            "profile_id": p.id,
            "pinned_snapshot_id": s.id,
            "title": "NVDA long?",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "consult"
    assert body["profile"]["id"] == p.id


@pytest.mark.django_db
def test_auto_reply_enqueues_ai_run_on_synthetic_snapshot_message(
    api, django_capture_on_commit_callbacks
):
    """auto_reply=true + a pinned snapshot streams an AI reply to the synthetic
    snapshot user-message — the 'ask' half of the composer's 'Capture + ask'."""
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    with (
        patch("apps.threads.views.run_ai_on_message.delay") as enqueue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        resp = api.post(
            "/api/threads/",
            {
                "kind": "consult",
                "profile_id": p.id,
                "pinned_snapshot_id": s.id,
                "auto_reply": True,
            },
            format="json",
        )
    assert resp.status_code == 201
    tid = resp.json()["id"]
    synthetic = Message.objects.get(thread_id=tid, role="user")
    enqueue.assert_called_once_with(thread_id=tid, user_message_id=synthetic.id)


@pytest.mark.django_db
def test_create_without_auto_reply_does_not_enqueue(api, django_capture_on_commit_callbacks):
    """Default thread-create (no auto_reply) stays silent — backward compatible."""
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    with (
        patch("apps.threads.views.run_ai_on_message.delay") as enqueue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        resp = api.post(
            "/api/threads/",
            {"kind": "consult", "profile_id": p.id, "pinned_snapshot_id": s.id},
            format="json",
        )
    assert resp.status_code == 201
    enqueue.assert_not_called()


@pytest.mark.django_db
def test_auto_reply_without_snapshot_does_not_enqueue(api, django_capture_on_commit_callbacks):
    """auto_reply with no pinned snapshot is a no-op: there is nothing to ask about."""
    p = TradingProfile.objects.create(name="P", style="x")
    with (
        patch("apps.threads.views.run_ai_on_message.delay") as enqueue,
        django_capture_on_commit_callbacks(execute=True),
    ):
        resp = api.post(
            "/api/threads/",
            {"kind": "consult", "profile_id": p.id, "auto_reply": True},
            format="json",
        )
    assert resp.status_code == 201
    enqueue.assert_not_called()


@pytest.mark.django_db
def test_send_message_enqueues_ai_run(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    with patch("apps.threads.views.run_ai_on_message.delay") as enqueue:
        enqueue.return_value.id = "task-1"
        r = api.post(f"/api/threads/{t.id}/send/", {"text": "hello"}, format="json")
    assert r.status_code == 202
    user_msg = Message.objects.get(thread=t, role="user")
    assert user_msg.content["text"] == "hello"
    enqueue.assert_called_once()
