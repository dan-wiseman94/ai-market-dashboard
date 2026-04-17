import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_profile_crud(api):
    resp = api.post("/api/profiles/", {
        "name": "A", "style": "x", "default_includes": ["quotes"],
    }, format="json")
    assert resp.status_code == 201
    pid = resp.json()["id"]

    assert len(api.get("/api/profiles/").json()) == 1
    api.patch(f"/api/profiles/{pid}/", {"name": "B"}, format="json")
    assert TradingProfile.objects.get(id=pid).name == "B"
