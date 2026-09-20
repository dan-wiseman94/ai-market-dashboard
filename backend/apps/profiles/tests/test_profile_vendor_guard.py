import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_create_profile_rejects_foreign_model(api):
    r = api.post(
        "/api/profiles/",
        {"name": "P", "style": "s", "default_provider": "openai", "default_model": "claude-opus-5"},
        format="json",
    )
    assert r.status_code == 400
    assert "claude catalog model" in r.json()["default_model"][0]


@pytest.mark.django_db
def test_create_profile_accepts_same_vendor_and_unknown_ids(api):
    ok = api.post(
        "/api/profiles/",
        {"name": "A", "style": "s", "default_provider": "openai", "default_model": "gpt-5.6-sol"},
        format="json",
    )
    assert ok.status_code == 201
    local = api.post(
        "/api/profiles/",
        {"name": "B", "style": "s", "default_provider": "local", "default_model": "llama-3.1-70b"},
        format="json",
    )
    assert local.status_code == 201


@pytest.mark.django_db
def test_patch_provider_alone_is_checked_against_stored_model(api):
    p = TradingProfile.objects.create(
        name="P", style="s", default_provider="claude", default_model="claude-opus-5"
    )
    r = api.patch(f"/api/profiles/{p.id}/", {"default_provider": "openai"}, format="json")
    assert r.status_code == 400
    assert "default_model" in r.json()
