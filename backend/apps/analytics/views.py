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
        if start_raw
        else end - timedelta(days=default_days)
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
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "forward_hours": hours,
                "rows": rows,
            }
        )


class CostPerInsightView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.cpi import cost_per_insight

        start, end = _parse_range(request, default_days=30)
        result = cost_per_insight(start=start, end=end)
        return Response({"start": start.isoformat(), "end": end.isoformat(), **result})


class TriggerHeatmapView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.trigger_heatmap import trigger_heatmap

        start, end = _parse_range(request, default_days=30)
        cells = trigger_heatmap(start=start, end=end)
        return Response({"start": start.isoformat(), "end": end.isoformat(), "cells": cells})


class ObserverTimelineView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.observer_timeline import observer_timeline

        start, end = _parse_range(request, default_days=30)
        days = observer_timeline(start=start, end=end)
        return Response({"start": start.isoformat(), "end": end.isoformat(), "days": days})


class UnusualOptionsView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.unusual_options import unusual_options

        ticker = (request.query_params.get("ticker") or "").strip()
        if not ticker:
            return Response({"rows": []})
        at_raw = request.query_params.get("at")
        at = datetime.fromisoformat(at_raw).replace(tzinfo=UTC) if at_raw else datetime.now(tz=UTC)
        try:
            top_n = max(1, min(100, int(request.query_params.get("top_n", "25"))))
        except ValueError:
            top_n = 25
        rows = unusual_options(ticker=ticker, at=at, top_n=top_n)
        return Response({"ticker": ticker.upper(), "at": at.isoformat(), "rows": rows})
