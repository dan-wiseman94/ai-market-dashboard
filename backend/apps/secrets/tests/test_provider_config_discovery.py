import pytest

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
def test_discovery_fields_roundtrip():
    pc = ProviderConfig.objects.create(provider="local", discovered_models=["llama3", "mistral"])
    pc.refresh_from_db()
    assert pc.discovered_models == ["llama3", "mistral"]
