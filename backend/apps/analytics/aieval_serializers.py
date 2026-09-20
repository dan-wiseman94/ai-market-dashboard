from typing import ClassVar

from rest_framework import serializers

from apps.analytics.models import EvalRun


class EvalRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvalRun
        fields: ClassVar = [
            "id",
            "created_at",
            "source",
            "label",
            "provider",
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


class EvalRunRequestSerializer(serializers.Serializer):
    """Body of ``POST /api/aieval/runs/`` — one manual, bounded, billed eval run."""

    provider = serializers.ChoiceField(choices=["claude", "openai", "local"], default="claude")
    model = serializers.CharField(required=False, allow_blank=True, default="")
    horizon = serializers.IntegerField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=100, default=25)
    # `label` is also the name of DRF's human-readable Field attribute, so declaring a
    # field by that name shadows a `str` on the base class.
    label = serializers.CharField(max_length=64, default="manual")  # type: ignore[assignment]

    def validate_horizon(self, value: int) -> int:
        from django.conf import settings

        allowed = list(settings.THESIS_POSTMORTEM_HORIZONS)
        if value not in allowed:
            raise serializers.ValidationError(f"horizon must be one of {allowed}")
        return value
