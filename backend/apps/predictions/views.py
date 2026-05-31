"""DRF views for apps.predictions (M13)."""

from __future__ import annotations

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.predictions.services.reconcile import ai_view_payload


class AIViewForTickerView(APIView):
    """The AI's current live call on a ticker, optionally reconciled against a
    thesis direction (``?against=bullish``). Powers the thesis-detail tile (F7)."""

    def get(self, request: Request) -> Response:
        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            return Response({"ticker": "", "has_view": False})
        against = request.query_params.get("against") or None
        return Response(ai_view_payload(ticker, against))
