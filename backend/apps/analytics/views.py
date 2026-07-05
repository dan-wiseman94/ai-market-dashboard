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
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                **cost_per_insight(start=start, end=end),
            }
        )


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
        # Frontend (useObserverTimeline) expects ``{days: [...]}``.
        days = observer_timeline(start=start, end=end)
        return Response({"start": start.isoformat(), "end": end.isoformat(), "days": days})


class UnusualOptionsView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.unusual_options import unusual_options

        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            return Response({"ticker": "", "rows": []})
        try:
            top_n = max(1, min(100, int(request.query_params.get("top_n", "25"))))
        except ValueError:
            top_n = 25

        _, end = _parse_range(request, default_days=1)
        # Frontend (useUnusualOptions) expects ``{rows: [...]}``.
        rows = unusual_options(ticker=ticker, at=end, top_n=top_n)
        return Response({"ticker": ticker, "at": end.isoformat(), "rows": rows})


class CalibrationView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.calibration import calibration

        start, end = _parse_range(request, default_days=90)
        try:
            horizon = int(request.query_params.get("horizon", "30"))
        except ValueError:
            horizon = 30
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                **calibration(start=start, end=end, horizon=horizon),
            }
        )


class CalibrationDrilldownView(APIView):
    """The theses behind a calibration bucket (scorecard drill-down)."""

    def get(self, request: Request) -> Response:
        from apps.analytics.services.calibration import calibration_drilldown

        start, end = _parse_range(request, default_days=90)
        try:
            horizon = int(request.query_params.get("horizon", "30"))
        except ValueError:
            horizon = 30
        raw_conviction = request.query_params.get("conviction")
        conviction = int(raw_conviction) if raw_conviction and raw_conviction.isdigit() else None
        direction = request.query_params.get("direction") or None
        verdict = request.query_params.get("verdict") or None
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                **calibration_drilldown(
                    start=start,
                    end=end,
                    horizon=horizon,
                    conviction=conviction,
                    direction=direction,
                    verdict=verdict,
                ),
            }
        )


class TrackRecordView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.calibration import track_record_for_ticker

        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            return Response({"ticker": "", "available": False, "record": None})
        direction = request.query_params.get("direction") or None
        conviction_raw = request.query_params.get("conviction")
        try:
            conviction = int(conviction_raw) if conviction_raw is not None else None
        except ValueError:
            conviction = None
        record = track_record_for_ticker(ticker, direction=direction, conviction=conviction)
        return Response({"ticker": ticker, "available": record is not None, "record": record})


def _opt_horizon(request: Request) -> int | None:
    raw = request.query_params.get("horizon")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


class AICalibrationView(APIView):
    """Live calibration of the AI's own resolved predictions."""

    def get(self, request: Request) -> Response:
        from apps.analytics.services.ai_calibration import ai_calibration

        start, end = _parse_range(request, default_days=90)
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                **ai_calibration(start=start, end=end, horizon=_opt_horizon(request)),
            }
        )


class AICalibrationDrilldownView(APIView):
    """The resolved predictions behind an AI-calibration band/slice."""

    def get(self, request: Request) -> Response:
        from apps.analytics.services.ai_calibration import ai_calibration_drilldown

        start, end = _parse_range(request, default_days=90)
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                **ai_calibration_drilldown(
                    start=start,
                    end=end,
                    horizon=_opt_horizon(request),
                    band=request.query_params.get("band") or None,
                    direction=request.query_params.get("direction") or None,
                    verdict=request.query_params.get("verdict") or None,
                    provider=request.query_params.get("provider") or None,
                    model=request.query_params.get("model") or None,
                ),
            }
        )


class TraderCalibrationView(APIView):
    """ "The Mirror" — grades the TRADER's own behavior from journal + thesis
    + post-mortem data. `?horizon=` (7/30/90, default 30)."""

    def get(self, request: Request) -> Response:
        from apps.analytics.services.trader_calibration import trader_calibration

        horizon_raw = request.query_params.get("horizon")
        try:
            horizon = int(horizon_raw) if horizon_raw else 30
        except ValueError:
            horizon = 30
        return Response(trader_calibration(horizon_days=horizon))


class CalibrationDriftView(APIView):
    """#14 — per-model calibration drift (recent vs baseline EvalRun error)."""

    def get(self, request: Request) -> Response:
        from apps.analytics.services.calibration_drift import calibration_drift

        try:
            window = max(7, min(180, int(request.query_params.get("window_days", "30"))))
        except (TypeError, ValueError):
            window = 30
        return Response(calibration_drift(window_days=window))


class ContradictionsView(APIView):
    """#15 — open predictions that oppose the ticker's house view (CoverageNote)."""

    def get(self, request: Request) -> Response:
        from apps.observer.predictions.services.consistency import open_contradictions

        return Response({"contradictions": open_contradictions()})
