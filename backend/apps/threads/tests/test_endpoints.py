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
    """Default thread-create (no auto_reply) stays silent."""
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
def test_patch_thread_renames_title(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="old")
    resp = api.patch(f"/api/threads/{t.id}/", {"title": "renamed"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["title"] == "renamed"
    t.refresh_from_db()
    assert t.title == "renamed"


@pytest.mark.django_db
def test_patch_thread_ignores_readonly_kind(api):
    """Only title is mutable; kind/pinned_snapshot are locked on update."""
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="x")
    resp = api.patch(f"/api/threads/{t.id}/", {"title": "y", "kind": "chat"}, format="json")
    assert resp.status_code == 200
    t.refresh_from_db()
    assert t.title == "y"
    assert t.kind == "consult"  # unchanged


@pytest.mark.django_db
def test_list_threads_is_paginated_and_omits_message_bodies(api):
    """The list endpoint must not serialize every thread's full message history
    (the heaviest over-fetch in the app — Message.content holds serialized
    snapshots + full AI responses). It returns a paginated envelope of light rows
    carrying a message_count, mirroring SnapshotViewSet; the detail view keeps the
    nested messages."""
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="T")
    Message.objects.create(thread=t, role="user", content={"text": "hi"}, status="done")
    Message.objects.create(thread=t, role="assistant", content={"text": "yo"}, status="done")

    resp = api.get("/api/threads/")
    assert resp.status_code == 200
    body = resp.json()
    # Paginated envelope (LimitOffsetPagination), not a bare array.
    assert set(body) >= {"count", "results"}
    assert body["count"] == 1
    row = body["results"][0]
    assert row["id"] == t.id
    assert row["profile"]["id"] == p.id
    assert "messages" not in row  # the whole point: no per-thread message payload
    assert row["message_count"] == 2


@pytest.mark.django_db
def test_retrieve_thread_includes_full_messages(api):
    """Retrieve keeps the full ThreadSerializer (messages nested) for the detail view."""
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="consult", profile=p, title="T")
    Message.objects.create(thread=t, role="user", content={"text": "hi"}, status="done")

    resp = api.get(f"/api/threads/{t.id}/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["messages"]) == 1
    assert body["messages"][0]["content"]["text"] == "hi"


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
