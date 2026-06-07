import pytest

from apps.strategy.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_create_and_defaults():
    e = DeskEntry.objects.create(anomaly_type="regime_change", severity=2.0, evidence={"x": 1})
    assert e.status == "new"
    assert e.ticker == ""
    assert "regime_change" in str(e)
