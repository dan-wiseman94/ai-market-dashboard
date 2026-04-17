from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread, Message


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_consult_thread(api):
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["quotes"], source="manual", status="ready")
    resp = api.post("/api/threads/", {
        "kind": "consult", "profile_id": p.id, "pinned_snapshot_id": s.id, "title": "NVDA long?",
    }, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "consult"
    assert body["profile"]["id"] == p.id


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
