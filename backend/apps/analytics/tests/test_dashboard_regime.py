import pytest
from rest_framework.test import APIClient

from apps.strategy.models import RegimeReading

pytestmark = pytest.mark.django_db


def test_dashboard_includes_regime_default_when_empty():
    body = APIClient().get("/api/dashboard/").json()
    assert "regime" in body
    assert body["regime"] == {"composite": None, "drivers": [], "as_of": None}


def test_dashboard_regime_populated():
    RegimeReading.objects.create(composite="Risk-On", axes={}, drivers=["VIX 12 — Low"])
    body = APIClient().get("/api/dashboard/").json()
    assert body["regime"]["composite"] == "Risk-On"
    assert body["regime"]["drivers"] == ["VIX 12 — Low"]
    assert body["regime"]["as_of"] is not None
