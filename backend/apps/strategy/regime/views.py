from __future__ import annotations

from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.strategy.models import RegimeReading
from apps.strategy.regime.serializers import RegimeReadingSerializer
from apps.strategy.regime.services.compute import compute_and_store, current_regime


class RegimeViewSet(ReadOnlyModelViewSet):
    """GET /api/regime/ (history), /current/ (latest or null), POST /refresh/."""

    queryset = RegimeReading.objects.all()
    serializer_class = RegimeReadingSerializer

    @action(detail=False, methods=["get"])
    def current(self, request: Request) -> Response | JsonResponse:
        reading = current_regime()
        if reading is None:
            # DRF's Response(None) renders an empty body; JsonResponse emits literal `null`
            # for the "latest-or-null" contract the frontend expects.
            return JsonResponse(None, safe=False)
        return Response(RegimeReadingSerializer(reading).data)

    @action(detail=False, methods=["post"])
    def refresh(self, request: Request) -> Response:
        reading = compute_and_store()
        return Response(RegimeReadingSerializer(reading).data)
