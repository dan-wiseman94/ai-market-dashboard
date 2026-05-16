from typing import ClassVar

from rest_framework import serializers

from apps.backups.models import BackupRecord


class BackupRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackupRecord
        fields: ClassVar = [
            "id",
            "created_at",
            "filename",
            "size_bytes",
            "sha256",
            "kind",
            "status",
            "error",
        ]
        read_only_fields: ClassVar = fields
