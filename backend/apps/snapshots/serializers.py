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


class SnapshotListSerializer(serializers.ModelSerializer):
    profile_name = serializers.CharField(source="profile.name", read_only=True)
    section_kinds = serializers.SerializerMethodField()
    section_statuses = serializers.SerializerMethodField()
    has_image = serializers.SerializerMethodField()
    total_payload_tokens = serializers.SerializerMethodField()

    class Meta:
        model = Snapshot
        fields: ClassVar = [
            "id",
            "captured_at",
            "profile_id",
            "profile_name",
            "objective",
            "notes",
            "status",
            "source",
            "primary_ticker",
            "section_kinds",
            "section_statuses",
            "has_image",
            "total_payload_tokens",
        ]

    def get_section_kinds(self, obj):
        return [s.kind for s in obj.sections.all()]

    def get_section_statuses(self, obj):
        return {s.kind: s.status for s in obj.sections.all()}

    def get_has_image(self, obj):
        return any(s.kind == "image" for s in obj.sections.all())

    def get_total_payload_tokens(self, obj):
        return sum(s.payload_tokens for s in obj.sections.all())


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
            "primary_ticker",
            "sections",
        ]
        read_only_fields: ClassVar = ["captured_at", "status"]
