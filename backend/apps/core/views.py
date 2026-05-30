"""Health, readiness, and error-event endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

if TYPE_CHECKING:
    from apps.core.models import ErrorEvent


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


def _serialize_error_event(ev: ErrorEvent) -> dict:
    return {
        "id": ev.pk,
        "level": ev.level,
        "source": ev.source,
        "message": ev.message,
        "fingerprint": ev.fingerprint,
        "resolved": ev.resolved,
        "created_at": ev.created_at.isoformat(),
    }


class ErrorEventListView(APIView):
    """GET /api/errors/ — list recent ErrorEvents newest-first.

    Query params:
      ?unresolved=true   — filter to unresolved only
      ?limit=N           — cap result count (default 50, max 200)
    """

    def get(self, request: Request) -> Response:
        from apps.core.models import ErrorEvent

        qs = ErrorEvent.objects.order_by("-created_at")
        if request.query_params.get("unresolved", "").lower() == "true":
            qs = qs.filter(resolved=False)

        try:
            limit = min(200, max(1, int(request.query_params.get("limit", "50"))))
        except ValueError:
            limit = 50

        events = list(qs[:limit])
        return Response(
            {
                "errors": [_serialize_error_event(ev) for ev in events],
                "count": len(events),
            }
        )


class ErrorEventResolveView(APIView):
    """POST /api/errors/<pk>/resolve/ — mark an ErrorEvent resolved."""

    def post(self, request: Request, pk: int) -> Response:
        from apps.core.models import ErrorEvent

        ev = get_object_or_404(ErrorEvent, pk=pk)
        ev.resolved = True
        ev.save(update_fields=["resolved"])
        return Response(_serialize_error_event(ev))
