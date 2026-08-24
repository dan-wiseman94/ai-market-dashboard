"""Shared HTTP helpers: query-param parsing + the {code, message} error envelope."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.http import HttpRequest, JsonResponse
from rest_framework.request import Request
from rest_framework.response import Response


def error_response(code: str, message: str = "", *, status: int) -> Response:
    """The standard ``{code, message}`` error envelope as a DRF ``Response``."""
    return Response({"code": code, "message": message}, status=status)


def json_error_response(code: str, message: str = "", *, status: int) -> JsonResponse:
    """The standard ``{code, message}`` error envelope as a ``JsonResponse``.

    Plain-Django function views must use this variant — a DRF ``Response``
    rendered outside a DRF view has no negotiated renderer.
    """
    return JsonResponse({"code": code, "message": message}, status=status)


def _parse_iso_utc(value: str) -> datetime:
    # Django's query-string parser decodes an unencoded '+' as a space; restore it
    # so timezone offsets like '+00:00' survive fromisoformat().
    dt = datetime.fromisoformat(value.replace(" ", "+"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_datetime_range(
    request: HttpRequest | Request,
    *,
    start_param: str = "start",
    end_param: str = "end",
    default_days: int,
) -> tuple[datetime, datetime]:
    """Read an ISO-8601 datetime range from query params, normalized to UTC.

    Naive values are treated as UTC; aware values are converted (not reinterpreted).
    Missing end defaults to now; missing start defaults to end - default_days.
    A malformed value raises ValueError — DRF callers surface it as a 400 via
    apps.core.exceptions.exception_handler.
    """
    params = request.query_params if isinstance(request, Request) else request.GET
    end_raw = params.get(end_param)
    start_raw = params.get(start_param)
    end = _parse_iso_utc(end_raw) if end_raw else datetime.now(tz=UTC)
    start = _parse_iso_utc(start_raw) if start_raw else end - timedelta(days=default_days)
    return start, end
