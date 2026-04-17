import pytest
from rest_framework.test import APIClient

from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_provider_config_create_does_not_leak_key(api):
    resp = api.post("/api/schwab/providers/", {
        "provider": "claude", "api_key_write": "sk-ant-xxx",
        "default_model": "claude-sonnet-4-6", "daily_cost_cap_usd": "5.00",
    }, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert "api_key" not in body
    assert body["api_key_present"] is True


@pytest.mark.django_db
def test_provider_config_update_key(api):
    ProviderConfig.objects.create(provider="claude")
    r = api.patch("/api/schwab/providers/claude/", {"api_key_write": "sk-ant-new"}, format="json")
    assert r.status_code == 200
    pc = ProviderConfig.objects.get(provider="claude")
    assert pc.api_key == "sk-ant-new"


@pytest.mark.django_db
def test_ai_models_endpoint(api):
    r = api.get("/api/schwab/models/?provider=claude")
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["models"]]
    assert "claude-sonnet-4-6" in ids
