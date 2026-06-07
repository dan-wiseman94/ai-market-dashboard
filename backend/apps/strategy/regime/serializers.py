from typing import ClassVar

from rest_framework import serializers

from apps.strategy.models import RegimeReading


class RegimeReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimeReading
        fields: ClassVar = [
            "id",
            "created_at",
            "composite",
            "axes",
            "drivers",
            "narrative",
            "changed_axes",
        ]
        read_only_fields: ClassVar = fields
