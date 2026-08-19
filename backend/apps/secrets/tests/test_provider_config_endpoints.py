import pytest
from rest_framework.test import APIClient

from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_provider_config_create_does_not_leak_key(api):
    resp = api.post(
        "/api/schwab/providers/",
        {
            "provider": "claude",
            "api_key_write": "sk-ant-xxx",
            "default_model": "claude-sonnet-4-6",
            "daily_cost_cap_usd": "5.00",
        },
        format="json",
    )
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


@pytest.mark.django_db
def test_provider_config_exposes_discovery_fields(api):
    ProviderConfig.objects.create(
        provider="local", base_url="http://x:11434/v1", discovered_models=["llama3"]
    )
    r = api.get("/api/schwab/providers/")
    assert r.status_code == 200
    row = next(c for c in r.json() if c["provider"] == "local")
    assert row["discovered_models"] == ["llama3"]
    assert "models_synced_at" in row


@pytest.mark.django_db
def test_discovery_fields_are_read_only(api):
    ProviderConfig.objects.create(provider="local", base_url="http://x:11434/v1")
    r = api.patch(
        "/api/schwab/providers/local/",
        {"discovered_models": ["injected"]},
        format="json",
    )
    assert r.status_code == 200
    pc = ProviderConfig.objects.get(provider="local")
    assert pc.discovered_models == []


def _corrupt_stored_key(provider: str) -> None:
    """Write non-Fernet bytes into the encrypted api_key column (raw SQL, literal
    names) to simulate a key/salt rotation that left the stored key undecryptable."""
    from django.db import connection

    assert ProviderConfig._meta.db_table == "secrets_providerconfig"
    assert ProviderConfig._meta.get_field("_api_key").column == "api_key"
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet-ciphertext", provider],
        )


@pytest.mark.django_db
def test_providers_list_tolerates_undecryptable_key(api):
    """A row whose key can't be decrypted must not 500 the list/detail endpoints —
    otherwise the Settings page is unusable and the user can't re-enter the key."""
    ProviderConfig.objects.create(provider="claude", default_model="claude-sonnet-4-6")
    _corrupt_stored_key("claude")

    r = api.get("/api/schwab/providers/")
    assert r.status_code == 200, r.content
    row = next(c for c in r.json() if c["provider"] == "claude")
    assert row["api_key_present"] is False  # unusable ⇒ reported absent to prompt re-entry

    r2 = api.get("/api/schwab/providers/claude/")
    assert r2.status_code == 200, r2.content


@pytest.mark.django_db
def test_can_reenter_key_over_undecryptable_row(api):
    """The point of tolerating the bad row: the user can PATCH a fresh key over it
    (re-encrypted with the current key) without hitting a 500."""
    ProviderConfig.objects.create(provider="claude", default_model="claude-sonnet-4-6")
    _corrupt_stored_key("claude")

    r = api.patch("/api/schwab/providers/claude/", {"api_key_write": "sk-ant-new"}, format="json")
    assert r.status_code == 200, r.content
    assert ProviderConfig.objects.get(provider="claude").api_key == "sk-ant-new"
