import pytest

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
def test_discovery_fields_default_empty():
    pc = ProviderConfig.objects.create(provider="local")
    assert pc.discovered_models == []
    assert pc.models_synced_at is None


@pytest.mark.django_db
def test_discovery_fields_roundtrip():
    pc = ProviderConfig.objects.create(
        provider="local", discovered_models=["llama3", "mistral"]
    )
    pc.refresh_from_db()
    assert pc.discovered_models == ["llama3", "mistral"]
