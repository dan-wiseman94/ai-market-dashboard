from rest_framework import serializers

from apps.regime.models import RegimeReading


class RegimeReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegimeReading
        fields = ["id", "created_at", "composite", "axes", "drivers", "narrative", "changed_axes"]
        read_only_fields = fields
