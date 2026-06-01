from typing import ClassVar

from rest_framework import serializers

from apps.desk.models import DeskEntry


class DeskEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = DeskEntry
        fields: ClassVar = [
            "id",
            "created_at",
            "anomaly_type",
            "ticker",
            "severity",
            "evidence",
            "finding",
            "suggested_actions",
            "status",
            "warroom_run_id",
            "investigation_thread_id",
        ]
        read_only_fields: ClassVar = fields
