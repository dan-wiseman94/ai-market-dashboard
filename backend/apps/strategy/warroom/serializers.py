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
        """Each argument with the model that made it; null for a message with no run
        (the verdict, whose one-shot AIRun carries no Message)."""
        out: list[dict] = []
        for m in obj.thread.messages.select_related("ai_run").order_by("created_at"):
            run = getattr(m, "ai_run", None)
            out.append(
                {
                    "role": m.role,
                    "content": m.content,
                    "provider": run.provider if run is not None else None,
                    "model": run.model if run is not None else None,
                }
            )
        return out
