import pytest

from apps.strategy.models import RegimeReading
from apps.strategy.regime.services.compute import current_regime

pytestmark = pytest.mark.django_db


def test_current_regime_returns_latest():
    RegimeReading.objects.create(composite="Risk-On", axes={"volatility": "Low"})
    latest = RegimeReading.objects.create(composite="Risk-Off", axes={"volatility": "Elevated"})
    assert current_regime().id == latest.id
