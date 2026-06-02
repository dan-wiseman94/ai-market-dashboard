from typing import ClassVar

from rest_framework import serializers

from apps.book.models import BookSnapshot


class BookSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookSnapshot
        fields: ClassVar = [
            "id",
            "created_at",
            "as_of_date",
            "exposures",
            "concentration",
            "clusters",
            "regime_fit",
            "near_invalidation",
            "narrative",
            "coverage",
            "var_beta",
        ]
        read_only_fields: ClassVar = fields
