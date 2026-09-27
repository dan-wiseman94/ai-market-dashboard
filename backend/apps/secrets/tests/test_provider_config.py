import pytest
from django.db import IntegrityError

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
def test_api_key_roundtrip_encrypted():
    pc = ProviderConfig.objects.create(provider="claude", api_key="sk-ant-xxx")  # type: ignore[misc]
    pc.refresh_from_db()
    assert pc.api_key == "sk-ant-xxx"


@pytest.mark.django_db
def test_one_row_per_provider():
    ProviderConfig.objects.create(provider="claude")
    with pytest.raises(IntegrityError):
        ProviderConfig.objects.create(provider="claude")
