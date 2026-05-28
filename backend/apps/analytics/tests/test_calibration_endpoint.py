import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_calibration_endpoint_shape(api):
    r = api.get("/api/analytics/calibration/")
    assert r.status_code == 200
    body = r.json()
    assert body["horizon"] == 30
    assert "start" in body and "end" in body
    assert "thesis" in body and "provider" in body
    assert len(body["thesis"]["buckets"]) == 5


@pytest.mark.django_db
def test_calibration_endpoint_clamps_invalid_horizon(api):
    assert api.get("/api/analytics/calibration/?horizon=999").json()["horizon"] == 30
    assert api.get("/api/analytics/calibration/?horizon=7").json()["horizon"] == 7
    assert api.get("/api/analytics/calibration/?horizon=90").json()["horizon"] == 90
