from decimal import Decimal

import pytest
from django.db import IntegrityError

from apps.secrets.models import ProviderConfig


@pytest.mark.django_db
def test_create_provider_config_defaults():
    pc = ProviderConfig.objects.create(provider="claude")
    assert pc.enabled is True
    assert pc.supports_vision is True
    assert pc.daily_cost_cap_usd == Decimal("10.00")
    assert pc.default_model == ""
    assert pc.base_url == ""


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
