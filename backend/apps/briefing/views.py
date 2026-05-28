from __future__ import annotations

from rest_framework import generics

from apps.briefing.models import BriefingConfig
from apps.briefing.serializers import BriefingConfigSerializer


class BriefingConfigView(generics.RetrieveUpdateAPIView):
    serializer_class = BriefingConfigSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self) -> BriefingConfig:
        return BriefingConfig.load()
