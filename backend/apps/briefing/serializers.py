from rest_framework import serializers

from apps.briefing.models import BriefingConfig


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
