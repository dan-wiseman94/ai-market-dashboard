"""Analytics DRF views. One view per analytic; each is a thin wrapper
around a service in apps.analytics.services.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


def _parse_range(request: Request, default_days: int) -> tuple[datetime, datetime]:
    now = datetime.now(tz=UTC)
    end_raw = request.query_params.get("end")
    start_raw = request.query_params.get("start")
    end = datetime.fromisoformat(end_raw).replace(tzinfo=UTC) if end_raw else now
    start = (
        datetime.fromisoformat(start_raw).replace(tzinfo=UTC)
        if start_raw else end - timedelta(days=default_days)
    )
    return start, end
