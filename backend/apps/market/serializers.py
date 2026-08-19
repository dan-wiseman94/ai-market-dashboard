from typing import ClassVar

from rest_framework import serializers

from apps.market.models import CalendarOverride


class CalendarOverrideSerializer(serializers.ModelSerializer):
    # API field is "ticker"; the model column stays "symbol" (extra_kwargs source keeps
    # the model-derived validators — max_length + UniqueValidator — on the renamed field).
    class Meta:
        model = CalendarOverride
        fields: ClassVar = ["id", "ticker", "market_key", "note", "created_at", "updated_at"]
        read_only_fields: ClassVar = ["created_at", "updated_at"]
        extra_kwargs: ClassVar = {"ticker": {"source": "symbol"}}
