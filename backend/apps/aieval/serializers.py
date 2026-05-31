from typing import ClassVar

from rest_framework import serializers

from apps.aieval.models import EvalRun


class EvalRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalRun
        fields: ClassVar = [
            "id",
            "created_at",
            "source",
            "label",
            "model",
            "horizon",
            "n",
            "skipped",
            "scored",
            "hit_rate",
            "brier",
            "avg_confidence",
            "calibration_error",
            "calibration",
            "examples",
        ]
        read_only_fields = fields
