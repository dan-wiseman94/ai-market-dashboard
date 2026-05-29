"""DRF serializers for EventTrigger + TriggerFiring."""

from __future__ import annotations

from typing import ClassVar

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.triggers.dsl import validate_condition
from apps.triggers.models import EventTrigger, TriggerFiring


class EventTriggerSerializer(serializers.ModelSerializer):
    firings_count = serializers.IntegerField(read_only=True, default=0)
    source_thesis_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = EventTrigger
        fields: ClassVar = [
            "id",
            "name",
            "profile",
            "condition",
            "cooldown_seconds",
            "enabled",
            "last_fired_at",
            "firings_count",
            "source_thesis_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields: ClassVar = [
            "id",
            "last_fired_at",
            "created_at",
            "updated_at",
            "firings_count",
            "source_thesis_id",
        ]

    def validate_condition(self, value):
        try:
            validate_condition(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value


class TriggerFiringSerializer(serializers.ModelSerializer):
    trigger_id = serializers.IntegerField(source="trigger.id", read_only=True)
    trigger_name = serializers.CharField(source="trigger.name", read_only=True)
    snapshot_id = serializers.IntegerField(read_only=True, allow_null=True)
    thread_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = TriggerFiring
        fields: ClassVar = [
            "id",
            "trigger_id",
            "trigger_name",
            "fired_at",
            "matched_values",
            "snapshot_id",
            "thread_id",
            "cost_capped",
        ]
        read_only_fields: ClassVar = fields
