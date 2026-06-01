import pytest
from rest_framework.test import APIClient

from apps.regime.models import RegimeReading

pytestmark = pytest.mark.django_db


def test_current_empty_returns_null():
    resp = APIClient().get("/api/regime/current/")
    assert resp.status_code == 200
    assert resp.json() is None


def test_current_returns_latest():
    RegimeReading.objects.create(composite="Risk-On", axes={"volatility": "Low"}, drivers=["VIX 12 — Low"])
    resp = APIClient().get("/api/regime/current/")
    body = resp.json()
    assert body["composite"] == "Risk-On"
    assert body["axes"]["volatility"] == "Low"
    assert "id" in body


def test_list_returns_history():
    RegimeReading.objects.create(composite="Risk-On", axes={})
    RegimeReading.objects.create(composite="Risk-Off", axes={})
    resp = APIClient().get("/api/regime/")
    rows = resp.json()
    assert len(rows) == 2
    assert rows[0]["composite"] == "Risk-Off"  # newest first (model ordering -created_at)


def test_refresh_endpoint_invokes_compute(monkeypatch):
    from apps.regime import views

    monkeypatch.setattr(
        views, "compute_and_store",
        lambda: RegimeReading.objects.create(composite="Stress", axes={}),
    )
    resp = APIClient().post("/api/regime/refresh/")
    assert resp.status_code == 200
    assert resp.json()["composite"] == "Stress"
