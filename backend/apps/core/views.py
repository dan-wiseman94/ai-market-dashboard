"""Health and readiness endpoints."""

from __future__ import annotations

import redis
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(_request: HttpRequest) -> JsonResponse:
    """Liveness: always 200 if the process is up."""
    return JsonResponse({"status": "ok"})


@require_GET
def ready(_request: HttpRequest) -> JsonResponse:
    """Readiness: per-dependency health."""
    db_status = _check_database()
    redis_status = _check_redis()
    overall_ok = db_status == "ok" and redis_status == "ok"
    status_code = 200 if overall_ok else 503
    return JsonResponse(
        {"database": db_status, "redis": redis_status},
        status=status_code,
    )


def _check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return "ok"
    except Exception:
        return "error"


def _check_redis() -> str:
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        client.ping()
        return "ok"
    except Exception:
        return "error"


@require_GET
def scenario_probe(_request: HttpRequest) -> JsonResponse:
    """Dev-only — echo the active scenario. Registered conditionally under MOCK_EXTERNAL."""
    from apps.core.mocks import current_scenario

    return JsonResponse({"scenario": current_scenario()})


@require_GET
def mock_ping_claude(_request: HttpRequest) -> JsonResponse:
    """Dev-only — drives the Claude mock dispatch for the active scenario and reports
    either the event count or the raised error kind. Used by the scenario-engine tests.
    """
    from apps.core.mocks import current_scenario
    from apps.core.mocks.providers import get_ai_stream_for_scenario

    try:
        events = get_ai_stream_for_scenario(current_scenario(), "claude")
    except Exception as exc:
        return JsonResponse(
            {"error_kind": type(exc).__name__, "detail": str(exc)},
            status=503,
        )
    return JsonResponse(
        {
            "events": len(events),
            "first_type": events[0].type if events else None,
            "scenario": current_scenario(),
        }
    )
