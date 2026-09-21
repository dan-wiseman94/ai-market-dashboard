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
    """Body of POST /api/aieval/runs/.

    Every field is optional so the UI can fire a run with an empty body; the view
    fills omissions from ``runtime_config()``. ``limit`` is bounded because the
    endpoint bills one model call per replayed row — the unbounded replay stays on
    ``manage.py aieval``, where the operator sees the row count first.
    """

    provider = serializers.ChoiceField(choices=["claude", "openai", "local"], required=False)
    model = serializers.CharField(max_length=128, required=False)
    horizon = serializers.ChoiceField(choices=[7, 30, 90], required=False, allow_null=True)
    limit = serializers.IntegerField(min_value=1, max_value=200, required=False)
    # Shadows rest_framework.fields.Field.label for mypy only — the serializer
    # metaclass pops declared fields off the class. The name matches the EvalRun
    # column and `manage.py aieval --label`, so keep it.
    label = serializers.CharField(max_length=64, required=False)  # type: ignore[assignment]
    system = serializers.CharField(max_length=8000, required=False)

    def validate(self, attrs):
        # A local endpoint serves user-declared names, so there is no catalog default
        # to fall back to — sending the configured Claude id would skip every row.
        if attrs.get("provider") == "local" and not attrs.get("model"):
            raise serializers.ValidationError({"model": "required when provider is 'local'"})
        return attrs


class EvalRunQueuedSerializer(serializers.Serializer):
    """202 body of POST /api/aieval/runs/: the Celery task id plus the fully
    resolved parameters the task was queued with (omissions already filled from
    ``runtime_config()``), so the caller sees what will actually be scored."""

    task_id = serializers.CharField()
    status = serializers.CharField(help_text='Always "queued".')
    provider = serializers.CharField()
    model = serializers.CharField()
    horizon = serializers.IntegerField(allow_null=True, help_text="null means every horizon.")
    limit = serializers.IntegerField()
    # Shadows rest_framework.fields.Field.label for mypy only — see the request
    # serializer above; the name matches the EvalRun column.
    label = serializers.CharField()  # type: ignore[assignment]
    system = serializers.CharField(
        allow_null=True, help_text="System-prompt override, or null for the default."
    )


class EvalRunRefusalSerializer(serializers.Serializer):
    """The reason a run was not queued: 409 under MOCK_EXTERNAL (a mocked run would
    persist a fabricated EvalRun that the coach and router then read as
    measurement), 429 when the provider's monthly cost cap is already hit."""

    detail = serializers.CharField()
