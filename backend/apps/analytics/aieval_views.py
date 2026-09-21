from __future__ import annotations

from cryptography.fernet import InvalidToken
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.catalog import default_model_for, foreign_model_error
from apps.ai.cost import CostCapExceededError
from apps.ai.structured import ensure_within_caps, resolve_structured_target
from apps.analytics.aieval_serializers import (
    EvalRunErrorSerializer,
    EvalRunQueuedSerializer,
    EvalRunRequestSerializer,
    EvalRunSerializer,
)
from apps.analytics.models import EvalRun
from apps.analytics.tasks import aieval_run
from apps.core.mocks import is_mock_mode
from apps.core.runtime_config import runtime_config


def _err(code: str, message: str, status: int) -> Response:
    return Response({"code": code, "message": message}, status=status)


class EvalRunListCreateView(generics.ListAPIView):
    """GET: the 50 newest runs. POST: queue one bounded, billed eval run on a provider."""

    serializer_class = EvalRunSerializer

    def get_queryset(self):
        return EvalRun.objects.order_by("-created_at")[:50]

    # The view's serializer_class describes the GET rows; the POST takes a request
    # body of its own and answers 202, so spell both out rather than let the schema
    # advertise the read serializer as the request contract.
    @extend_schema(
        request=EvalRunRequestSerializer,
        responses={
            202: EvalRunQueuedSerializer,
            400: EvalRunErrorSerializer,
            409: EvalRunErrorSerializer,
        },
        methods=["POST"],
    )
    def post(self, request):
        ser = EvalRunRequestSerializer(data=request.data)
        if not ser.is_valid():
            # One error shape for this endpoint: the UI reads `code`/`message`, and a
            # bare DRF field-error dict would surface as an empty toast.
            field, messages = next(iter(ser.errors.items()))
            return _err("invalid_request", f"{field}: {messages[0]}", 400)
        d = ser.validated_data

        # The harness reaches the provider through run_structured, which has NO
        # MOCK_EXTERNAL short-circuit — a run queued under the e2e overlay would
        # persist a fabricated EvalRun that the coach and the calibration-weighted
        # router then read as measurement.
        if is_mock_mode():
            return _err("mock_mode", "Eval runs are unavailable in MOCK_EXTERNAL mode.", 409)

        rc = runtime_config()
        provider: str = d["provider"]
        model: str = d["model"] or default_model_for(provider)
        # An explicit null means "every horizon"; an omitted key inherits the
        # UI-configurable default (SystemSettings ?? AIEVAL_SCHEDULED_HORIZON).
        horizon: int | None = d.get("horizon", rc.aieval_scheduled_horizon)
        limit: int = d.get("limit") or rc.aieval_scheduled_limit

        err = foreign_model_error(provider, model)
        if err:
            return _err("foreign_model", err, 400)
        try:
            target = resolve_structured_target(override_provider=provider, override_model=model)
        except InvalidToken:
            return _err(
                "undecryptable_key",
                f"The stored {provider} key cannot be decrypted; re-enter it in "
                "Settings → AI Providers.",
                400,
            )
        if target is None:
            need = "a base URL" if provider == "local" else "an API key"
            return _err(
                "no_provider",
                f"No usable {provider} target: add {need} and a default model, and enable "
                "it in Settings → AI Providers.",
                400,
            )
        # Preflight here as well as in the task: a capped provider should be refused
        # at the click, not silently queued and dropped.
        try:
            ensure_within_caps(target)
        except CostCapExceededError:
            return _err("cost_cap", "Cost cap exceeded for the selected provider.", 409)

        # Queue the RESOLVED target, not the requested one: `default_model_for("local")`
        # is "" by design, and the resolver is what chains in the ProviderConfig's own
        # default. Queueing the request's blank id would run the eval against no model.
        params = {
            "provider": target.provider,
            "model": target.model,
            "horizon": horizon,
            "limit": limit,
            "label": d["label"],
        }
        # Only passed when asked for, so the task keeps its documented default prompt.
        system = d.get("system")
        aieval_run.delay(**params, **({"system": system} if system else {}))
        return Response({"queued": True, **params}, status=drf_status.HTTP_202_ACCEPTED)


class EvalRunLatestView(APIView):
    def get(self, request):
        run = EvalRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(EvalRunSerializer(run).data)
