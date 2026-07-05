"""Malformed-input exceptions map to 4xx, not 500."""

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile, Watchlist
from apps.snapshots.models import Snapshot


@pytest.mark.django_db
def test_delete_profile_with_protected_dependents_returns_409():
    profile = TradingProfile.objects.create(name="prot", style="s")
    Snapshot.objects.create(profile=profile, status="ready")  # Snapshot.profile is PROTECT
    r = APIClient().delete(f"/api/profiles/{profile.id}/")
    assert r.status_code == 409


@pytest.mark.django_db
def test_non_integer_detail_pk_is_4xx_not_500():
    r = APIClient().get("/api/threads/not-a-number/")
    assert r.status_code in (400, 404)


@pytest.mark.django_db
def test_thread_create_with_non_object_body_returns_400():
    r = APIClient().post("/api/threads/", [1, 2, 3], format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_reorder_with_non_object_body_returns_400():
    wl = Watchlist.objects.create(name="wl")
    r = APIClient().post(f"/api/watchlists/{wl.id}/reorder/", [1, 2, 3], format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_missing_object_via_get_returns_404():
    # observer.read does Notification.objects.get(id=pk) — a raw DoesNotExist must 404.
    r = APIClient().post("/api/observer/notifications/999999/read/")
    assert r.status_code == 404


@pytest.mark.django_db
def test_action_with_non_object_body_returns_400():
    # threads.send → _user_text(request.data.get(...)) crashes on a non-dict body.
    thread_resp = APIClient().post("/api/threads/", {}, format="json")
    tid = thread_resp.json()["id"]
    r = APIClient().post(f"/api/threads/{tid}/send/", [1, 2, 3], format="json")
    assert r.status_code == 400
