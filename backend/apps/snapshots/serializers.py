from rest_framework import serializers

from .models import Snapshot, SnapshotSection


class SnapshotSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SnapshotSection
        fields = ["id", "kind", "status", "payload", "error"]


class SnapshotSerializer(serializers.ModelSerializer):
    sections = SnapshotSectionSerializer(many=True, read_only=True)

    class Meta:
        model = Snapshot
        fields = [
            "id", "profile_id", "objective", "notes", "status", "includes",
            "source", "captured_at", "sections",
        ]
        read_only_fields = ["captured_at", "status"]
