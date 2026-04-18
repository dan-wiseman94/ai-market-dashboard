import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.threads.models import Message


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_observer_thread_endpoint_creates_on_first_call(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp = api.get(f"/api/observer/threads/{p.id}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "observer"
    assert body["profile_id"] == p.id


@pytest.mark.django_db
def test_observer_thread_endpoint_idempotent(api):
    p = TradingProfile.objects.create(name="P", style="x")
    resp1 = api.get(f"/api/observer/threads/{p.id}/")
    resp2 = api.get(f"/api/observer/threads/{p.id}/")
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.django_db
def test_observer_thread_endpoint_includes_messages(api):
    from apps.observer.services.threads import get_or_create_observer_thread
    p = TradingProfile.objects.create(name="P", style="x")
    t = get_or_create_observer_thread(p)
    Message.objects.create(thread=t, role="user", content={"text": "snap1"})
    Message.objects.create(thread=t, role="assistant", content={"text": "ok"})
    resp = api.get(f"/api/observer/threads/{p.id}/")
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 2
