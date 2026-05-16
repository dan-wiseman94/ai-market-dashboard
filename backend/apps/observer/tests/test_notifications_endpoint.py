import pytest
from rest_framework.test import APIClient

from apps.observer.models import Notification


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_list_notifications_returns_anonymous_only(api):
    Notification.objects.create(user=None, kind="error", title="anon")
    resp = api.get("/api/observer/notifications/")
    assert resp.status_code == 200
    body = resp.json()
    items = body.get("results", body) if isinstance(body, dict) else body
    assert len(items) == 1


@pytest.mark.django_db
def test_list_unread_filter(api):
    from django.utils import timezone

    Notification.objects.create(user=None, kind="error", title="unread")
    Notification.objects.create(user=None, kind="error", title="read", read_at=timezone.now())
    resp = api.get("/api/observer/notifications/?unread=true")
    assert resp.status_code == 200
    body = resp.json()
    items = body.get("results", body) if isinstance(body, dict) else body
    titles = [n["title"] for n in items]
    assert "unread" in titles and "read" not in titles


@pytest.mark.django_db
def test_mark_one_read(api):
    n = Notification.objects.create(user=None, kind="error", title="x")
    resp = api.post(f"/api/observer/notifications/{n.id}/read/")
    assert resp.status_code == 200
    n.refresh_from_db()
    assert n.read_at is not None


@pytest.mark.django_db
def test_mark_all_read(api):
    Notification.objects.create(user=None, kind="error", title="a")
    Notification.objects.create(user=None, kind="error", title="b")
    resp = api.post("/api/observer/notifications/mark-all-read/")
    assert resp.status_code == 200
    assert Notification.objects.filter(read_at__isnull=True).count() == 0
