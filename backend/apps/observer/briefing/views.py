from __future__ import annotations

from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.observer.briefing.serializers import BriefingConfigSerializer, BriefingRunSerializer
from apps.observer.briefing.services.run import run_briefing
from apps.observer.models import BriefingConfig, BriefingRun


class BriefingConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = BriefingConfigSerializer
    # Tuple (not list) so RUF012 doesn't demand ClassVar — which mypy rejects here,
    # since django-stubs types View.http_method_names as an instance Sequence[str].
    http_method_names = ("get", "patch", "head", "options")

    def get_object(self) -> BriefingConfig:
        return BriefingConfig.load()


class BriefingListView(generics.ListAPIView):
    serializer_class = BriefingRunSerializer

    def get_queryset(self):
        return BriefingRun.objects.select_related("synthesis_message").order_by("-created_at")[:30]


class BriefingLatestView(APIView):
    def get(self, request):
        run = BriefingRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(BriefingRunSerializer(run).data)


class BriefingRunNowView(APIView):
    def post(self, request):
        run = run_briefing(scheduled=False)
        return Response(BriefingRunSerializer(run).data, status=drf_status.HTTP_201_CREATED)
