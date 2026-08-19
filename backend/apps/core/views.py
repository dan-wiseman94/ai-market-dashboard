"""Health, readiness, and error-event endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis
from django.conf import settings
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
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
                "results": [_serialize_error_event(ev) for ev in events],
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


class SystemSettingsView(APIView):
    """GET/PATCH /api/settings/ — runtime-tunable knobs (retention, AI resilience/failover,
    observer cache, scheduled eval). GET returns the resolved *effective* values (UI override
    where set, else the env/settings default). PATCH writes explicit overrides; values take
    effect on the next task run / request — no worker/beat restart.
    """

    def get(self, _request: Request) -> Response:
        from dataclasses import asdict

        from apps.core.runtime_config import runtime_config

        return Response(asdict(runtime_config()))

    def patch(self, request: Request) -> Response:
        from dataclasses import asdict

        from apps.core.models import SystemSettings
        from apps.core.runtime_config import EDITABLE_FIELDS, runtime_config

        cfg = SystemSettings.load()
        changed: list[str] = []
        for key, value in request.data.items():
            if key not in EDITABLE_FIELDS:
                return Response(
                    {"code": "unknown_field", "message": f"Unknown field: {key}"}, status=400
                )
            coerced, err = _coerce_setting(key, value, EDITABLE_FIELDS[key])
            if err is not None:
                return Response({"code": "invalid_value", "message": err}, status=400)
            setattr(cfg, key, coerced)
            changed.append(key)
        if changed:
            cfg.save(update_fields=[*changed, "updated_at"])
        return Response(asdict(runtime_config()))


def _coerce_setting(key: str, value: object, typ: type) -> tuple[object, str | None]:
    """Coerce/validate a single PATCH value. None clears the override (inherit default)."""
    if value is None:
        return None, None
    try:
        if typ is bool:
            if not isinstance(value, bool):
                return None, f"{key} must be a boolean"
            return value, None
        if typ is int:
            coerced: object = int(value)  # type: ignore[call-overload]
        elif typ is float:
            coerced = float(value)  # type: ignore[arg-type]
        else:
            coerced = str(value)
    except (TypeError, ValueError):
        return None, f"{key} must be {typ.__name__}"
    if typ in (int, float) and coerced < 0:  # type: ignore[operator]
        return None, f"{key} must be >= 0"
    if key.startswith("retention_") and typ is int:
        # 0 days would make the next prune delete EVERY row of that model; use
        # null to disable pruning instead. OHLC is read by date by post-mortems,
        # so its floor must clear the longest post-mortem horizon.
        if coerced < 1:  # type: ignore[operator]
            return None, f"{key} must be >= 1 (use null to disable pruning)"
        if key == "retention_ohlc_days":
            floor = max(settings.THESIS_POSTMORTEM_HORIZONS) + 7
            if coerced < floor:  # type: ignore[operator]
                return None, (
                    f"retention_ohlc_days must be >= {floor}: post-mortems resolve "
                    "against OHLC bars by date up to the longest horizon"
                )
    return coerced, None


@csrf_exempt
@require_POST
def mcp_endpoint(request: HttpRequest):
    """MCP-out server: a minimal JSON-RPC 2.0 endpoint exposing the second
    brain (house view / theses / predictions / recall) as read-only MCP tools.

    Auth: the app's posture is network isolation (127.0.0.1 + AllowAny). This is the
    one endpoint built for EXTERNAL agents, so it adds an OPT-IN shared-token gate:
    set MCP_AUTH_TOKEN and clients must send ``Authorization: Bearer <token>``. Unset
    (default) preserves the localhost single-user flow — set it before exposing the
    server beyond localhost (e.g. via a tunnel)."""
    import hmac
    import json

    from apps.core.mcp import handle

    token = getattr(settings, "MCP_AUTH_TOKEN", "") or ""
    if token:
        auth = request.headers.get("Authorization", "")
        provided = auth[7:] if auth.startswith("Bearer ") else ""
        if not hmac.compare_digest(provided, token):  # constant-time
            return JsonResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32001, "message": "Unauthorized"},
                },
                status=401,
            )

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status=400,
        )
    resp = handle(payload)
    if resp is None:  # a notification — accepted, no body
        return HttpResponse(status=202)
    return JsonResponse(resp)
