import pytest
from django.test import Client


@pytest.mark.django_db
def test_health_returns_ok():
    """GET /api/health/ returns 200 with status ok."""
    client = Client()
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_reports_dependency_status():
    """GET /api/ready/ returns per-dep status."""
    client = Client()
    response = client.get("/api/ready/")
    assert response.status_code in (200, 503)
    body = response.json()
    assert "database" in body
    assert "redis" in body
    assert body["database"] in ("ok", "error")
    assert body["redis"] in ("ok", "error")
