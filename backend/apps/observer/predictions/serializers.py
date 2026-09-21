"""DRF serializers for the Prediction Ledger."""

from __future__ import annotations

from typing import ClassVar

from rest_framework import serializers

from apps.observer.models import AIPrediction


class AIPredictionSerializer(serializers.ModelSerializer):
    """One ledger row, read-only: predictions are written by the extractor and
    scored by the resolver, never by a client."""

    source_message_id = serializers.IntegerField(read_only=True, allow_null=True)
    source_snapshot_id = serializers.IntegerField(read_only=True, allow_null=True)
    profile_id = serializers.IntegerField(read_only=True, allow_null=True)
    profile_name = serializers.CharField(source="profile.name", read_only=True, default="")

    class Meta:
        model = AIPrediction
        fields: ClassVar = [
            "id",
            "ticker",
            "direction",
            "horizon_days",
            "confidence",
            "expected_move_pct",
            "rationale",
            "invalidation_price",
            "invalidation_note",
            "provider",
            "model",
            "status",
            "predicted_at",
            "resolve_at",
            "resolved_at",
            "invalidated_at",
            "forward_return_pct",
            "verdict",
            "source_message_id",
            "source_snapshot_id",
            "profile_id",
            "profile_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = fields


class PredictionFiltersSerializer(serializers.Serializer):
    """The ledger filters as actually applied — not as sent. An unknown status or a
    non-numeric horizon is dropped rather than rejected, so each key is null when
    the corresponding filter was absent or ignored."""

    ticker = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=AIPrediction.STATUSES, allow_null=True)
    horizon = serializers.IntegerField(allow_null=True)


class PredictionCountsSerializer(serializers.Serializer):
    """Counts over one cohort of ledger rows. ``hit_rate`` and
    ``avg_forward_return_pct`` are null rather than 0.0 when nothing is decisive —
    ``mixed`` and ``inconclusive`` are not scored either way."""

    open = serializers.IntegerField()
    resolving = serializers.IntegerField()
    resolved = serializers.IntegerField()
    invalidated = serializers.IntegerField()
    correct = serializers.IntegerField()
    incorrect = serializers.IntegerField()
    mixed = serializers.IntegerField()
    inconclusive = serializers.IntegerField()
    total = serializers.IntegerField()
    avg_forward_return_pct = serializers.FloatField(allow_null=True)
    hit_rate = serializers.FloatField(allow_null=True)


class PredictionTickerStatsSerializer(PredictionCountsSerializer):
    """One per-ticker row of the rollup, busiest ticker first."""

    ticker = serializers.CharField()


class PredictionStatsSerializer(serializers.Serializer):
    """Body of GET /api/predictions/stats/."""

    filters = PredictionFiltersSerializer()
    totals = PredictionCountsSerializer()
    by_ticker = PredictionTickerStatsSerializer(many=True)
