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


class LeaderboardView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.leaderboard import provider_leaderboard
        start, end = _parse_range(request, default_days=30)
        try:
            hours = max(1, min(168, int(request.query_params.get("forward_hours", "24"))))
        except ValueError:
            hours = 24
        rows = provider_leaderboard(start=start, end=end, forward_hours=hours)
        return Response({
            "start": start.isoformat(), "end": end.isoformat(),
            "forward_hours": hours, "rows": rows,
        })
