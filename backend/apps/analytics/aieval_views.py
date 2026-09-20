from __future__ import annotations

from cryptography.fernet import InvalidToken
from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.catalog import default_model_for, foreign_model_error
from apps.ai.cost import CostCapExceededError
from apps.ai.structured import ensure_within_caps, resolve_structured_target
from apps.analytics.aieval_serializers import EvalRunRequestSerializer, EvalRunSerializer
from apps.analytics.models import EvalRun
from apps.analytics.tasks import aieval_run


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
    @extend_schema(request=EvalRunRequestSerializer, responses={202: None}, methods=["POST"])
    def post(self, request):
        ser = EvalRunRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        provider: str = d["provider"]
        model: str = d["model"] or default_model_for(provider)
        horizon: int = d.get("horizon") or settings.AIEVAL_SCHEDULED_HORIZON

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
                f"No usable {provider} provider: add {need} and enable it in "
                "Settings → AI Providers.",
                400,
            )
        # Preflight here as well as in the task: a capped provider should be refused
        # at the click, not silently queued and dropped.
        try:
            ensure_within_caps(target)
        except CostCapExceededError as exc:
            return _err("cost_cap", str(exc), 409)

        aieval_run.delay(
            provider=provider, model=model, horizon=horizon, limit=d["limit"], label=d["label"]
        )
        return Response(
            {
                "queued": True,
                "provider": provider,
                "model": model,
                "horizon": horizon,
                "limit": d["limit"],
                "label": d["label"],
            },
            status=drf_status.HTTP_202_ACCEPTED,
        )


class EvalRunLatestView(APIView):
    def get(self, request):
        run = EvalRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(EvalRunSerializer(run).data)
