from typing import ClassVar

from rest_framework import serializers

from apps.market.models import CalendarOverride


class CalendarOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarOverride
        fields: ClassVar = ["id", "symbol", "market_key", "note", "created_at", "updated_at"]
        read_only_fields: ClassVar = ["created_at", "updated_at"]
