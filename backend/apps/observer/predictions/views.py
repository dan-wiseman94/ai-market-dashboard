"""DRF views for the Prediction Ledger."""

from __future__ import annotations

from django.db.models import Avg, Count, Q, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observer.models import AIPrediction
from apps.observer.predictions.serializers import (
    AIPredictionSerializer,
    PredictionStatsSerializer,
)
from apps.observer.predictions.services.reconcile import ai_view_payload, open_divergences

STATUSES = {value for value, _ in AIPrediction.STATUSES}

# The list and the stats rollup read the same three filters off the query string, so
# they declare the same parameters. Declared here rather than per-view so the two can
# never drift apart in the contract the way they could in prose.
LEDGER_FILTER_PARAMS = [
    OpenApiParameter(
        "ticker",
        str,
        description="Exact ticker, case-insensitive. Ignored when blank.",
    ),
    OpenApiParameter(
        "status",
        str,
        enum=sorted(STATUSES),
        description="Ledger status. An unrecognized value is ignored, not rejected.",
    ),
    OpenApiParameter(
        "horizon",
        int,
        description="Horizon in days (matches horizon_days). A non-numeric value is ignored.",
    ),
]


class _PredictionPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def _filtered(params) -> tuple[QuerySet[AIPrediction], dict]:
    """Apply the shared ``ticker``/``status``/``horizon`` filters. Returns the
    queryset plus the filters as applied, so a caller can echo them back."""
    qs = AIPrediction.objects.all()
    applied: dict[str, object] = {"ticker": None, "status": None, "horizon": None}

    ticker = (params.get("ticker") or "").strip().upper()
    if ticker:
        qs = qs.filter(ticker=ticker)
        applied["ticker"] = ticker

    status = (params.get("status") or "").strip().lower()
    if status in STATUSES:
        qs = qs.filter(status=status)
        applied["status"] = status

    raw_horizon = (params.get("horizon") or "").strip()
    if raw_horizon.isdigit():
        horizon = int(raw_horizon)
        qs = qs.filter(horizon_days=horizon)
        applied["horizon"] = horizon

    return qs, applied


@extend_schema(parameters=LEDGER_FILTER_PARAMS)
class PredictionListView(generics.ListAPIView):
    """Browse the ledger: ``?ticker=``, ``?status=`` (open/resolving/resolved/
    invalidated), ``?horizon=`` (days). Newest call first. An unknown status or a
    non-numeric horizon is ignored rather than 400ing — these are URL-driven UI
    filters, not a contract."""

    serializer_class = AIPredictionSerializer
    pagination_class = _PredictionPagination

    def get_queryset(self):
        qs, _ = _filtered(self.request.query_params)
        return qs.select_related("profile").order_by("-predicted_at", "-id")


class PredictionDetailView(generics.RetrieveAPIView):
    serializer_class = AIPredictionSerializer
    queryset = AIPrediction.objects.select_related("profile")


def _hit_rate(correct: int, incorrect: int) -> float | None:
    """Decisive-only hit rate, matching the cohort/calibration convention:
    ``mixed`` and ``inconclusive`` are not scored either way. None below one
    decisive call rather than a fabricated 0.0."""
    decisive = correct + incorrect
    return round(correct / decisive, 4) if decisive else None


_COUNT_AGGREGATES = {
    "open": Count("id", filter=Q(status="open")),
    "resolving": Count("id", filter=Q(status="resolving")),
    "resolved": Count("id", filter=Q(status="resolved")),
    "invalidated": Count("id", filter=Q(status="invalidated")),
    "correct": Count("id", filter=Q(verdict="correct")),
    "incorrect": Count("id", filter=Q(verdict="incorrect")),
    "mixed": Count("id", filter=Q(verdict="mixed")),
    "inconclusive": Count("id", filter=Q(verdict="inconclusive")),
    "total": Count("id"),
    "avg_forward_return_pct": Avg("forward_return_pct"),
}


def _row(src: dict) -> dict:
    out = {k: src.get(k) or 0 for k in _COUNT_AGGREGATES if k != "avg_forward_return_pct"}
    avg = src.get("avg_forward_return_pct")
    out["avg_forward_return_pct"] = round(avg, 4) if avg is not None else None
    out["hit_rate"] = _hit_rate(out["correct"], out["incorrect"])
    return out


class PredictionStatsView(APIView):
    """Ledger rollup: overall counts + per-ticker hit rate, under the same
    ``ticker``/``status``/``horizon`` filters as the list. Two aggregate queries
    total — no per-ticker fan-out."""

    # A bare APIView has no serializer_class for drf-spectacular to guess from, so
    # without this the whole rollup documents as "no response body" and the frontend
    # types it as unknown.
    @extend_schema(
        parameters=LEDGER_FILTER_PARAMS,
        responses={200: PredictionStatsSerializer},
    )
    def get(self, request: Request) -> Response:
        qs, applied = _filtered(request.query_params)
        totals = _row(qs.aggregate(**_COUNT_AGGREGATES))
        by_ticker = [
            {"ticker": row["ticker"], **_row(row)}
            for row in qs.values("ticker").annotate(**_COUNT_AGGREGATES)
        ]
        # Busiest ticker first. Sorted here rather than in SQL: the rows are already
        # one-per-ticker and django-stubs can't resolve an annotation alias in order_by().
        by_ticker.sort(key=lambda row: (-row["total"], row["ticker"]))
        return Response({"filters": applied, "totals": totals, "by_ticker": by_ticker})


class AIViewForTickerView(APIView):
    """The AI's current live call on a ticker, optionally reconciled against a
    thesis direction (``?against=bullish``). Powers the thesis-detail tile."""

    def get(self, request: Request) -> Response:
        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            return Response({"ticker": "", "has_view": False})
        against = request.query_params.get("against") or None
        return Response(ai_view_payload(ticker, against))


class DivergencesView(APIView):
    """Open theses that conflict with the AI's current call — the dashboard
    divergence rollup. ``?partial=false`` to show only hard diverges."""

    def get(self, request: Request) -> Response:
        include_partial = request.query_params.get("partial", "true") != "false"
        rows = open_divergences(include_partial=include_partial)
        return Response({"count": len(rows), "rows": rows})
