"""Contract tests for GET /api/ready/ — readiness endpoint.

These tests lock the public contract so a refactor cannot silently break it.
We do NOT change the compose healthcheck to point at /api/ready/ because
beat depends_on web: service_healthy, and redirecting the healthcheck to
/api/ready/ risks a startup-ordering deadlock (DB/redis not up when web
first starts). The health check stays on /api/health/ (liveness only);
/api/ready/ is the richer contract tested here and used by operators/monitors.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_ready_happy_path_status_200() -> None:
    """GET /api/ready/ returns 200 when DB and redis are reachable."""
    client = Client()
    response = client.get("/api/ready/")
    # In the test environment DB is always up (pytest-django sets it up).
    # Redis may or may not be available — accept 200 only when both are ok.
    # If this fails 503 in CI it means the test environment itself is broken,
    # not the endpoint contract.
    assert response.status_code == 200


@pytest.mark.django_db
def test_ready_happy_path_response_shape() -> None:
    """Response body must contain exactly {database, redis} with string values."""
    client = Client()
    response = client.get("/api/ready/")
    body = response.json()
    assert "database" in body, "response must contain 'database' key"
    assert "redis" in body, "response must contain 'redis' key"
    assert body["database"] in ("ok", "error"), f"unexpected database value: {body['database']}"
    assert body["redis"] in ("ok", "error"), f"unexpected redis value: {body['redis']}"


@pytest.mark.django_db
def test_ready_happy_path_db_ok() -> None:
    """database key reports 'ok' when the DB is reachable (always true under pytest-django)."""
    client = Client()
    response = client.get("/api/ready/")
    body = response.json()
    assert body["database"] == "ok"


@pytest.mark.django_db
def test_ready_method_not_allowed() -> None:
    """Only GET is allowed; POST must return 405."""
    client = Client()
    response = client.post("/api/ready/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_ready_503_when_db_down() -> None:
    """When the DB check raises, /api/ready/ must return 503 with database='error'."""
    client = Client()
    with patch("apps.core.views._check_database", return_value="error"):
        response = client.get("/api/ready/")
    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "error"


@pytest.mark.django_db
def test_ready_503_when_redis_down() -> None:
    """When the redis check raises, /api/ready/ must return 503 with redis='error'."""
    client = Client()
    with patch("apps.core.views._check_redis", return_value="error"):
        response = client.get("/api/ready/")
    assert response.status_code == 503
    body = response.json()
    assert body["redis"] == "error"


@pytest.mark.django_db
def test_ready_200_only_when_both_ok() -> None:
    """200 is returned only when both database and redis report 'ok'."""
    client = Client()
    with (
        patch("apps.core.views._check_database", return_value="ok"),
        patch("apps.core.views._check_redis", return_value="ok"),
    ):
        response = client.get("/api/ready/")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
