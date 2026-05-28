from typing import ClassVar

from rest_framework import serializers

from .models import Snapshot, SnapshotImage, SnapshotSection


class SnapshotSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnapshotSection
        fields: ClassVar = ["id", "kind", "status", "payload", "error"]


class SnapshotImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnapshotImage
        fields: ClassVar = ["id", "kind", "caption", "created_at", "snapshot_id"]
        read_only_fields: ClassVar = ["created_at"]


class SnapshotSerializer(serializers.ModelSerializer):
    sections = SnapshotSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Snapshot
        fields: ClassVar = [
            "id",
            "profile_id",
            "objective",
            "notes",
            "manual_positions",
            "status",
            "includes",
            "source",
            "captured_at",
            "sections",
        ]
        read_only_fields: ClassVar = ["captured_at", "status"]
