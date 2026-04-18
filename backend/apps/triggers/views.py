"""Triggers HTTP endpoints."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.triggers import evaluator, metrics
from apps.triggers.dsl import validate_condition
from apps.triggers.models import EventTrigger
from apps.triggers.serializers import EventTriggerSerializer
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


def _synthetic_trigger(condition: dict, *, profile_id: int | None) -> EventTrigger:
    """A detached EventTrigger used only for metrics.build_snapshot() leaf-walking.

    Not saved to the DB. Used by the `evaluate` action when the caller passes a
    raw DSL body rather than a saved trigger id.
    """
    return EventTrigger(name="__dryrun__", profile_id=profile_id or 0, condition=condition)
