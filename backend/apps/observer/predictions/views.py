"""DRF views for the Prediction Ledger."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observer.predictions.services.reconcile import ai_view_payload, open_divergences


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
