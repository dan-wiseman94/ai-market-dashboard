"""ViewSet for the Portfolio app — manual position record-keeping."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.market.returns import latest_closes
from apps.thesis.portfolio_serializers import PositionSerializer
from apps.thesis.portfolio_service import realized_pnl

from .models import Position


def _error(code: str, message: str, status: int) -> Response:
    return Response({"code": code, "message": message}, status=status)


class PositionViewSet(viewsets.ModelViewSet):
    """CRUD + close action for manually maintained positions.

    Filters:
      ?status=open|closed
      ?ticker=NVDA
      ?thesis=<id>
    """

    serializer_class = PositionSerializer

    def get_queryset(self):  # type: ignore[override]
        qs = Position.objects.select_related("thesis", "profile").order_by("-opened_at")
        params = self.request.query_params

        status = params.get("status")
        if status:
            qs = qs.filter(status=status)

        ticker = params.get("ticker")
        if ticker:
            qs = qs.filter(ticker=ticker.upper())

        thesis_id = params.get("thesis")
        if thesis_id:
            try:
                qs = qs.filter(thesis_id=int(thesis_id))
            except (ValueError, TypeError):
                return qs.none()

        return qs

    def list(self, request: Request, *args, **kwargs) -> Response:  # type: ignore[override]
        # Resolve the latest OHLC close once for all tickers (instead of one query per
        # row in the serializer) so the query count stays constant in the number of
        # positions returned. Kept as a comment, not a docstring, so it does not override
        # the ViewSet's OpenAPI operation description (which would drift backend/schema.yml).
        positions = list(self.filter_queryset(self.get_queryset()))
        prices = latest_closes({p.ticker for p in positions}, timezone.now())
        serializer = self.get_serializer(
            positions,
            many=True,
            context={**self.get_serializer_context(), "position_prices": prices},
        )
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def close(self, request: Request, pk: str | None = None) -> Response:
        """Close a position.

        Body:
          close_price  (required) — Decimal string or number
          closed_at    (optional) — ISO 8601 datetime string; defaults to now

        Sets status="closed", close_price, closed_at, realized_pnl (computed).
        Returns the updated row.
        """
        position = self.get_object()

        raw_price = request.data.get("close_price")
        if raw_price is None:
            return _error("missing_field", "close_price is required", 400)

        try:
            close_price = Decimal(str(raw_price))
        except InvalidOperation:
            return _error("invalid_value", "close_price must be a valid number", 400)

        # Optional explicit closed_at
        raw_closed_at = request.data.get("closed_at")
        if raw_closed_at:
            from django.utils.dateparse import parse_datetime

            closed_at = parse_datetime(str(raw_closed_at))
            if closed_at is None:
                return _error("invalid_value", "closed_at must be a valid ISO 8601 datetime", 400)
        else:
            closed_at = timezone.now()

        pnl = realized_pnl(
            avg_cost=position.avg_cost,
            close_price=close_price,
            quantity=position.quantity,
            direction=position.direction,
        )

        position.status = "closed"
        position.close_price = close_price
        position.closed_at = closed_at
        position.realized_pnl = pnl
        position.save()

        return Response(PositionSerializer(position).data, status=200)
