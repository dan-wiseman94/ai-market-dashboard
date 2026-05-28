from rest_framework import serializers

from apps.briefing.models import BriefingConfig, BriefingRun


class BriefingConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = BriefingConfig
        fields = [
            "enabled",
            "send_at_local",
            "profile",
            "news_lookback_hours",
            "events_within_days",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class BriefingRunSerializer(serializers.ModelSerializer):
    synthesis_text = serializers.SerializerMethodField()
    synthesis_status = serializers.SerializerMethodField()

    class Meta:
        model = BriefingRun
        fields = [
            "id",
            "created_at",
            "status",
            "data",
            "snapshot",
            "scheduled_date",
            "synthesis_text",
            "synthesis_status",
        ]

    def get_synthesis_text(self, obj) -> str:
        m = obj.synthesis_message
        return (m.content or {}).get("text", "") if m else ""

    def get_synthesis_status(self, obj) -> str:
        return obj.synthesis_message.status if obj.synthesis_message else ""
