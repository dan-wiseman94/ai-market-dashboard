import pytest
from django.conf import settings
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
    assert body["horizons"] == list(settings.THESIS_POSTMORTEM_HORIZONS)
    assert "start" in body and "end" in body
    assert "thesis" in body and "provider" in body
    assert len(body["thesis"]["buckets"]) == 5


@pytest.mark.django_db
def test_calibration_family_endpoints_expose_horizon_set(api):
    """The FE derives its horizon pickers from the payload's `horizons` field."""
    expected = list(settings.THESIS_POSTMORTEM_HORIZONS)
    for url in (
        "/api/analytics/calibration/",
        "/api/analytics/calibration/drilldown/",
        "/api/analytics/trader-calibration/",
    ):
        assert api.get(url).json()["horizons"] == expected


@pytest.mark.django_db
def test_calibration_endpoint_clamps_invalid_horizon(api):
    assert api.get("/api/analytics/calibration/?horizon=999").json()["horizon"] == 30
    assert api.get("/api/analytics/calibration/?horizon=7").json()["horizon"] == 7
    assert api.get("/api/analytics/calibration/?horizon=90").json()["horizon"] == 90
