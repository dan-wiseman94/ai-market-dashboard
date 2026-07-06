"""Observer DRF serializers."""

from typing import ClassVar

from croniter import croniter  # type: ignore[import-untyped]
from rest_framework import serializers

from .models import Notification, ObserverSchedule


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields: ClassVar = [
            "id",
            "kind",
            "title",
            "body",
            "link",
            "meta",
            "read_at",
            "created_at",
        ]
        read_only_fields: ClassVar = ["created_at"]


class ObserverScheduleSerializer(serializers.ModelSerializer):
    cron = serializers.CharField(write_only=True, required=False)
    cron_display = serializers.SerializerMethodField()

    class Meta:
        model = ObserverSchedule
        fields: ClassVar = [
            "id",
            "name",
            "profile",
            "enabled",
            "market_hours_only",
            "objective_template",
            "override_provider",
            "override_model",
            "default_includes",
            "default_watchlist_tickers",
            "mode",
            "structured",
            "use_batch",
            "consensus",
            "investigate",
            "last_batch_id",
            "last_fired_at",
            "created_at",
            "updated_at",
            "fire_mode",
            "close_offset_minutes",
            "cron",
            "cron_display",
        ]
        read_only_fields: ClassVar = [
            "last_fired_at",
            "last_batch_id",
            "created_at",
            "updated_at",
        ]

    def get_cron_display(self, obj) -> str:
        from apps.observer.services.sync import crontab_to_cron

        pt = obj.periodic_task
        if pt is None or pt.crontab is None:
            return ""
        return crontab_to_cron(pt.crontab)

    def validate_cron(self, value: str) -> str:
        if len(value.split()) != 5:
            raise serializers.ValidationError("cron must be a 5-field expression")
        try:
            croniter(value)
        except (ValueError, KeyError) as e:
            raise serializers.ValidationError(f"invalid cron expression: {e}") from e
        return value

    def validate(self, attrs):
        fire_mode = attrs.get("fire_mode") or (self.instance.fire_mode if self.instance else "cron")
        has_existing_pt = bool(self.instance and self.instance.periodic_task)
        if fire_mode == "cron" and not attrs.get("cron") and not has_existing_pt:
            raise serializers.ValidationError({"cron": "cron is required for cron fire_mode"})
        self._validate_claude_only_modes(attrs)
        return attrs

    def _validate_claude_only_modes(self, attrs) -> None:
        """structured / use_batch run through Anthropic APIs (messages.parse /
        Messages Batches); reject at configuration time rather than letting
        every fire 401 against api.anthropic.com with a non-Claude key."""
        from apps.ai.catalog import CLAUDE_FAMILY_PROVIDERS

        structured = self._resolved(attrs, "structured", default=False)
        use_batch = self._resolved(attrs, "use_batch", default=False)
        if not structured and not use_batch:
            return
        profile = self._resolved(attrs, "profile", default=None)
        provider = self._resolved(attrs, "override_provider", default="") or getattr(
            profile, "default_provider", ""
        )
        if provider not in CLAUDE_FAMILY_PROVIDERS:
            field = "structured" if structured else "use_batch"
            raise serializers.ValidationError(
                {
                    field: (
                        f"{field} requires a Claude provider; this schedule "
                        f"resolves to {provider!r}"
                    )
                }
            )

    def _resolved(self, attrs, field: str, *, default):
        """The value this write resolves to: incoming attr, else the current
        instance value (PATCH omits unchanged fields), else the default."""
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field)
        return default
