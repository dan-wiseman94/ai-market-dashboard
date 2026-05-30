"""Triggers HTTP endpoints."""

from __future__ import annotations

from datetime import UTC

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.triggers import evaluator, metrics
from apps.triggers.dsl import validate_condition
from apps.triggers.models import EventTrigger, TriggerFiring
from apps.triggers.serializers import EventTriggerSerializer, TriggerFiringSerializer
from apps.triggers.tasks import fire_trigger


class EventTriggerViewSet(viewsets.ModelViewSet):
    serializer_class = EventTriggerSerializer

    def get_queryset(self):
        return (
            EventTrigger.objects.select_related("profile")
            .annotate(firings_count=Count("firings"))
            .order_by("-created_at")
        )

    @action(detail=True, methods=["post"])
    def fire(self, request: Request, pk: str | None = None) -> Response:
        trigger = self.get_object()
        if not trigger.enabled:
            return Response(
                {"code": "disabled", "message": "Enable the trigger before firing manually."},
                status=400,
            )
        task = fire_trigger.delay(trigger_id=trigger.id, matched_values={"source": "manual"})
        return Response({"task_id": str(task.id)}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=["post"])
    def evaluate(self, request: Request) -> Response:
        """Dry-run: run the evaluator against a condition without firing.

        Body: {condition: <DSL>, profile?: <id>} OR {trigger_id: <id>}.
        Returns {matched, values, missing}.
        """
        data = request.data
        if "trigger_id" in data:
            try:
                trigger = EventTrigger.objects.get(id=data["trigger_id"])
            except EventTrigger.DoesNotExist:
                return Response({"code": "not_found"}, status=404)
            condition = trigger.condition
        else:
            condition = data.get("condition")
            if condition is None:
                return Response({"code": "missing_condition"}, status=400)
            try:
                validate_condition(condition)
            except DjangoValidationError as exc:
                return Response({"code": "invalid_condition", "message": str(exc)}, status=400)
            trigger = _synthetic_trigger(condition, profile_id=data.get("profile"))

        snapshot = metrics.build_snapshot([trigger])
        matched, values = evaluator.evaluate(condition, snapshot)
        missing = [k for k, v in values.items() if v is None]
        return Response({"matched": matched, "values": values, "missing": missing})

    @action(detail=True, methods=["get"])
    def firings(self, request: Request, pk: str | None = None) -> Response:
        trigger = self.get_object()
        qs = trigger.firings.select_related("snapshot", "thread").order_by("-fired_at")
        try:
            page = max(1, int(request.query_params.get("page", "1")))
            size = max(1, min(50, int(request.query_params.get("size", "20"))))
        except ValueError:
            page, size = 1, 20
        total = qs.count()
        start = (page - 1) * size
        rows = qs[start : start + size]
        return Response(
            {
                "results": TriggerFiringSerializer(rows, many=True).data,
                "count": total,
                "page": page,
                "size": size,
            }
        )

    @action(detail=False, methods=["post"])
    def backtest(self, request: Request) -> Response:
        """Replay a DSL condition over stored OHLC bars for [start, end].

        Body: {condition, start (ISO date), end (ISO date), timeframe?}
        Returns {match_count, matches:[{ts, values}]}. Only price/pct_change
        leaves are evaluated; other metrics are silently absent from the
        per-bar snapshot.
        """
        from datetime import datetime

        from apps.triggers.backtest import backtest as run_backtest

        data = request.data
        condition = data.get("condition")
        if condition is None:
            return Response({"code": "missing_condition"}, status=400)
        try:
            validate_condition(condition)
        except DjangoValidationError as exc:
            return Response({"code": "invalid_condition", "message": str(exc)}, status=400)

        try:
            start = datetime.fromisoformat(str(data["start"])).replace(tzinfo=UTC)
            end = datetime.fromisoformat(str(data["end"])).replace(tzinfo=UTC)
        except (KeyError, ValueError) as exc:
            return Response({"code": "bad_dates", "message": str(exc)}, status=400)

        from apps.triggers.backtest import backtest_summary

        timeframe = data.get("timeframe", "1d")
        matches = run_backtest(condition, start=start, end=end, timeframe=timeframe)
        return Response(
            {
                "match_count": len(matches),
                "matches": [
                    {
                        "ts": m.ts.isoformat(),
                        "values": m.values,
                        "fwd_1d_pct": m.fwd_1d_pct,
                        "fwd_5d_pct": m.fwd_5d_pct,
                    }
                    for m in matches[:500]
                ],
                "summary": backtest_summary(matches),
            }
        )

    @action(detail=False, methods=["get"], url_path="firings/recent")
    def firings_recent(self, request: Request) -> Response:
        try:
            limit = max(1, min(20, int(request.query_params.get("limit", "5"))))
        except ValueError:
            limit = 5
        qs = TriggerFiring.objects.select_related("trigger", "snapshot", "thread").order_by(
            "-fired_at"
        )[:limit]
        return Response(TriggerFiringSerializer(qs, many=True).data)


def _synthetic_trigger(condition: dict, *, profile_id: int | None) -> EventTrigger:
    """A detached EventTrigger used only for metrics.build_snapshot() leaf-walking.

    Not saved to the DB. Used by the `evaluate` action when the caller passes a
    raw DSL body rather than a saved trigger id.
    """
    return EventTrigger(name="__dryrun__", profile_id=profile_id or 0, condition=condition)
