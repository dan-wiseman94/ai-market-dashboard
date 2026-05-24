"""Health + readiness contract."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_health_endpoint_returns_200(api_client) -> None:
    r = api_client.get("/api/health/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@pytest.mark.integration
def test_ready_endpoint_reports_dependencies(api_client) -> None:
    r = api_client.get("/api/ready/")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "database" in body
    assert "redis" in body
