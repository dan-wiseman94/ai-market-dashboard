import pytest

from apps.secrets.models import ProviderConfig
from apps.secrets.serializers import ProviderConfigSerializer


@pytest.mark.django_db
def test_supports_tools_defaults_true():
    cfg = ProviderConfig.objects.create(provider="openai")
    assert cfg.supports_tools is True


@pytest.mark.django_db
def test_supports_tools_in_serializer():
    cfg = ProviderConfig.objects.create(
        provider="local", base_url="http://x/v1", supports_tools=False
    )
    data = ProviderConfigSerializer(cfg).data
    assert data["supports_tools"] is False
