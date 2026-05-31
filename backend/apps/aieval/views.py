from __future__ import annotations

from rest_framework import generics
from rest_framework import status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.aieval.models import EvalRun
from apps.aieval.serializers import EvalRunSerializer


class EvalRunListView(generics.ListAPIView):
    serializer_class = EvalRunSerializer

    def get_queryset(self):
        return EvalRun.objects.order_by("-created_at")[:50]


class EvalRunLatestView(APIView):
    def get(self, request):
        run = EvalRun.objects.order_by("-created_at").first()
        if run is None:
            return Response(status=drf_status.HTTP_204_NO_CONTENT)
        return Response(EvalRunSerializer(run).data)
