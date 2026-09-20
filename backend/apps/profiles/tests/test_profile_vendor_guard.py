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
def test_create_with_provider_only_is_checked_against_the_model_default(api):
    """An omitted default_model persists the model's own default (a Claude id), so a
    create that names only a non-Claude provider must not slip past the guard."""
    r = api.post(
        "/api/profiles/", {"name": "P", "style": "s", "default_provider": "openai"}, format="json"
    )
    assert r.status_code == 400
    assert "default_model" in r.json()


@pytest.mark.django_db
def test_patch_of_an_unrelated_field_is_not_blocked_by_a_legacy_mismatch(api):
    """A profile already storing another vendor's model stays editable: the Activate
    control PATCHes only `active`, and must not fail on a field it never touched."""
    p = TradingProfile.objects.create(
        name="Legacy", style="s", default_provider="openai", default_model="claude-sonnet-4-6"
    )
    r = api.patch(f"/api/profiles/{p.id}/", {"active": False}, format="json")
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.active is False


@pytest.mark.django_db
def test_patch_provider_alone_is_checked_against_stored_model(api):
    p = TradingProfile.objects.create(
        name="P", style="s", default_provider="claude", default_model="claude-opus-5"
    )
    r = api.patch(f"/api/profiles/{p.id}/", {"default_provider": "openai"}, format="json")
    assert r.status_code == 400
    assert "default_model" in r.json()
