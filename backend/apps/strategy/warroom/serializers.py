from typing import ClassVar

from rest_framework import serializers

from apps.strategy.models import WarRoomRun


class WarRoomRunSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()
    # Derived from verdict["confidence"] (not a stored column); serialized on the
    # API for the list view's confidence badge.
    confidence = serializers.SerializerMethodField()

    class Meta:
        model = WarRoomRun
        fields: ClassVar = [
            "id",
            "created_at",
            "subject_kind",
            "subject_label",
            "params",
            "verdict",
            "confidence",
            "status",
            "error",
            "thread_id",
            "messages",
        ]
        read_only_fields: ClassVar = fields

    def get_confidence(self, obj) -> float | None:
        return (obj.verdict or {}).get("confidence")

    def get_messages(self, obj) -> list[dict]:
        return [
            {"role": m.role, "content": m.content}
            for m in obj.thread.messages.all().order_by("created_at")
        ]
