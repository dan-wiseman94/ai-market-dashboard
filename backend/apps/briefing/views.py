from __future__ import annotations

from typing import ClassVar

from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.briefing.models import BriefingConfig, BriefingRun
from apps.briefing.serializers import BriefingConfigSerializer, BriefingRunSerializer
from apps.briefing.services.run import run_briefing


class BriefingConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = BriefingConfigSerializer
    http_method_names: ClassVar = ["get", "patch", "head", "options"]

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
