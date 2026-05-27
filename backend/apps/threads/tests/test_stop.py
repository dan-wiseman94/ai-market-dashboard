import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_stop_streaming_message(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": ""}, status="streaming")

    r = api.post(f"/api/threads/{t.id}/stop/{m.id}/", format="json")
    assert r.status_code == 200
    m.refresh_from_db()
    assert m.status == "failed"
    assert m.error == "cancelled"


@pytest.mark.django_db
def test_stop_already_terminal_is_idempotent(api):
    # A stop that lands after the run already finished (UI race or a dropped WS
    # leaving a stale "streaming" button) is a benign no-op, not a client error.
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": "ok"}, status="done")

    r = api.post(f"/api/threads/{t.id}/stop/{m.id}/", format="json")
    assert r.status_code == 200
    assert r.json()["already_terminal"] is True
    m.refresh_from_db()
    assert m.status == "done"  # untouched — we did not flip a finished message to "failed"
    assert not m.error


@pytest.mark.django_db
def test_stop_missing_message_is_404(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")

    r = api.post(f"/api/threads/{t.id}/stop/999999/", format="json")
    assert r.status_code == 404
