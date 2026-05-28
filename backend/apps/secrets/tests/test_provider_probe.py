from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest
from rest_framework.test import APIClient

from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_probe_success_persists_and_returns_models(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["llama3", "mistral"]))
    with patch("apps.secrets.views.get_provider", return_value=fake):
        r = api.post("/api/schwab/providers/local/probe/", {}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["models"] == ["llama3", "mistral"]
    assert body["synced_at"]
    pc = ProviderConfig.objects.get(provider="local")
    assert pc.discovered_models == ["llama3", "mistral"]
    assert pc.models_synced_at is not None


@pytest.mark.django_db
def test_probe_persists_base_url_from_body(api):
    ProviderConfig.objects.create(provider="local", base_url="")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["a"]))
    with patch("apps.secrets.views.get_provider", return_value=fake) as gp:
        r = api.post(
            "/api/schwab/providers/local/probe/",
            {"base_url": "http://new:11434/v1"},
            format="json",
        )
    assert r.status_code == 200
    assert ProviderConfig.objects.get(provider="local").base_url == "http://new:11434/v1"
    assert gp.call_args.kwargs["base_url"] == "http://new:11434/v1"


@pytest.mark.django_db
def test_probe_connection_error_is_friendly(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    err = openai.APIConnectionError(request=httpx.Request("GET", "http://x"))
    fake = SimpleNamespace(list_models=AsyncMock(side_effect=err))
    with patch("apps.secrets.views.get_provider", return_value=fake):
        r = api.post("/api/schwab/providers/local/probe/", {}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Couldn't reach" in body["error"]


@pytest.mark.django_db
def test_probe_missing_base_url_is_400(api):
    ProviderConfig.objects.create(provider="local", base_url="")
    r = api.post("/api/schwab/providers/local/probe/", {}, format="json")
    assert r.status_code == 400
    assert r.json()["ok"] is False


@pytest.mark.django_db
def test_probe_does_not_leak_api_key(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    fake = SimpleNamespace(list_models=AsyncMock(return_value=["a"]))
    with patch("apps.secrets.views.get_provider", return_value=fake):
        r = api.post(
            "/api/schwab/providers/local/probe/",
            {"api_key_write": "secret-xyz"},
            format="json",
        )
    assert "secret-xyz" not in r.text
    assert "api_key" not in r.json()
