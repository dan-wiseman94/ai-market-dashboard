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
