from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.catalog import default_model_for, get_model
from apps.ai.cost import CostCapExceededError
from apps.analytics.aieval_serializers import (
    EvalRunQueuedSerializer,
    EvalRunRefusalSerializer,
    EvalRunRequestSerializer,
    EvalRunSerializer,
)
from apps.analytics.models import EvalRun
from apps.analytics.services.aieval import preflight_cost_cap
from apps.analytics.tasks import run_manual
from apps.core.mocks.providers import is_mock_mode
from apps.core.runtime_config import runtime_config


def _model_for(provider: str, configured: str) -> str:
    """``configured`` unless it is a catalog row of a different provider — then that
    provider's own default. Mirrors run_structured's target resolution, so a Claude
    model id left over from the scheduled harness is never sent to OpenAI."""
    if configured and get_model(provider, configured) is not None:
        return configured
    return default_model_for(provider) or configured


class EvalRunListView(generics.ListAPIView):
    """GET: the recent eval runs. POST: queue one against a candidate (provider,
    model, system prompt) and return the Celery task id."""

    def get_serializer_class(self):
        if self.request.method == "POST":
            return EvalRunRequestSerializer
        return EvalRunSerializer

    def get_queryset(self):
        return EvalRun.objects.order_by("-created_at")[:50]

    # get_serializer_class() hands the request serializer to both directions, so
    # without this the POST documents its own request body as the response. The run
    # is queued, never awaited: 202, not 200.
    @extend_schema(
        request=EvalRunRequestSerializer,
        responses={
            202: EvalRunQueuedSerializer,
            409: EvalRunRefusalSerializer,
            429: EvalRunRefusalSerializer,
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # run_structured hands back a canned instance under MOCK_EXTERNAL, so a run
        # queued here would persist a fabricated EvalRun that the coach and the
        # calibration-weighted router then read as measurement.
        if is_mock_mode():
            return Response(
                {"detail": "eval runs are unavailable in MOCK_EXTERNAL mode"},
                status=drf_status.HTTP_409_CONFLICT,
            )

        rc = runtime_config()
        provider = data.get("provider") or "claude"
        params = {
            "provider": provider,
            "model": data.get("model") or _model_for(provider, rc.aieval_scheduled_model),
            # An explicit null means "every horizon"; an omitted key inherits.
            "horizon": data.get("horizon", rc.aieval_scheduled_horizon),
            "limit": data.get("limit") or rc.aieval_scheduled_limit,
            "label": data.get("label") or "manual",
            "system": data.get("system") or None,
        }

        # Pre-flight on the request thread so a capped user gets the reason instead of
        # a queued task that silently no-ops. The task re-checks before spending.
        try:
            preflight_cost_cap(provider)
        except CostCapExceededError as exc:
            return Response({"detail": str(exc)}, status=drf_status.HTTP_429_TOO_MANY_REQUESTS)

        task = run_manual.delay(**params)
        return Response(
            {"task_id": str(task.id), "status": "queued", **params},
            status=drf_status.HTTP_202_ACCEPTED,
        )


class EvalRunLatestView(APIView):
    def get(self, request):
        run = EvalRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(EvalRunSerializer(run).data)
