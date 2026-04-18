"""Observer DRF serializers."""
from typing import ClassVar

from rest_framework import serializers

from .models import Notification, ObserverSchedule


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields: ClassVar = [
            "id", "kind", "title", "body", "link", "meta", "read_at", "created_at",
        ]
        read_only_fields: ClassVar = ["created_at"]


class ObserverScheduleSerializer(serializers.ModelSerializer):
    """Stub — full impl in Task 11."""
    class Meta:
        model = ObserverSchedule
        fields: ClassVar = ["id", "name", "profile", "enabled"]
