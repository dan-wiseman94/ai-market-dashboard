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
    """Body of ``POST /api/aieval/runs/`` — one manual, bounded, billed eval run.

    Every field is optional so the UI can fire a run with an empty body; the view
    fills the omissions from ``runtime_config()`` and resolves the target through
    the provider's own config. ``limit`` is bounded because the endpoint bills one
    model call per replayed row — the unbounded replay stays on ``manage.py
    aieval``, where the operator sees the row count first.
    """

    provider = serializers.ChoiceField(choices=["claude", "openai", "local"], default="claude")
    model = serializers.CharField(required=False, allow_blank=True, default="")
    # Explicit null means "every horizon"; an omitted key inherits the configured one.
    horizon = serializers.IntegerField(required=False, allow_null=True)
    limit = serializers.IntegerField(min_value=1, max_value=100, required=False)
    # `label` is also the name of DRF's human-readable Field attribute, so declaring a
    # field by that name shadows a `str` on the base class.
    label = serializers.CharField(max_length=64, default="manual")  # type: ignore[assignment]
    system = serializers.CharField(
        max_length=8000,
        required=False,
        help_text="System-prompt override for A/B-ing a prompt; omit for the default.",
    )

    def validate_horizon(self, value: int | None) -> int | None:
        from django.conf import settings

        # DRF runs validate_<field> even for an explicit null, which here means
        # "every horizon" rather than a horizon to check against the allow-list.
        if value is None:
            return None
        allowed = list(settings.THESIS_POSTMORTEM_HORIZONS)
        if value not in allowed:
            raise serializers.ValidationError(f"horizon must be one of {allowed}")
        return value


class EvalRunQueuedSerializer(serializers.Serializer):
    """202 body of ``POST /api/aieval/runs/``: the fully resolved parameters the task
    was queued with (omissions filled from ``runtime_config()``, the model resolved
    through the provider's own config), so the caller sees what will be scored."""

    queued = serializers.BooleanField(help_text="Always true.")
    provider = serializers.CharField()
    model = serializers.CharField()
    horizon = serializers.IntegerField(allow_null=True, help_text="null means every horizon.")
    limit = serializers.IntegerField()
    # Shadows rest_framework.fields.Field.label for mypy only — see the request
    # serializer above; the name matches the EvalRun column.
    label = serializers.CharField()  # type: ignore[assignment]


class EvalRunErrorSerializer(serializers.Serializer):
    """The reason a run was not queued. One error shape for the endpoint, so the UI
    always has a message to show: 400 for a body or provider that cannot resolve to a
    usable target, 409 for a breached cost cap or for MOCK_EXTERNAL (a mocked run
    would persist a fabricated EvalRun that the coach and the calibration-weighted
    router then read as measurement)."""

    code = serializers.CharField(
        help_text="invalid_request | foreign_model | undecryptable_key | no_provider | "
        "cost_cap | mock_mode"
    )
    message = serializers.CharField()
