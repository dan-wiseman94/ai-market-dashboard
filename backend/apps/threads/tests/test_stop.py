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
def test_stop_rejects_non_streaming(api):
    p = TradingProfile.objects.create(name="P", style="x")
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    m = Message.objects.create(thread=t, role="assistant", content={"text": "ok"}, status="done")

    r = api.post(f"/api/threads/{t.id}/stop/{m.id}/", format="json")
    assert r.status_code == 400
