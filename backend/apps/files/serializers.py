from typing import ClassVar

from rest_framework import serializers

from apps.files.models import UserFile


class UserFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFile
        fields: ClassVar = [
            "id",
            "anthropic_id",
            "kind",
            "ticker",
            "mime",
            "size",
            "filename",
            "uploaded_at",
        ]
        read_only_fields: ClassVar = ["id", "anthropic_id", "mime", "size", "uploaded_at"]
