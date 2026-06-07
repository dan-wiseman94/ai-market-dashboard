from typing import ClassVar

from rest_framework import mixins, viewsets
from rest_framework.serializers import ModelSerializer

from apps.thesis.models import Lesson


class LessonSerializer(ModelSerializer):
    class Meta:
        model = Lesson
        # embedding (the 384-float vector) is deliberately not exposed.
        fields: ClassVar = ["id", "text", "tags", "support_n", "muted", "last_seen", "created_at"]
        read_only_fields: ClassVar = ["id", "text", "tags", "support_n", "last_seen", "created_at"]


class LessonViewSet(
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,  # PATCH `muted` only (others read-only)
    mixins.DestroyModelMixin,  # prune a noisy lesson
    viewsets.GenericViewSet,
):
    """Read + prune/mute the distilled lessons — the hygiene surface for M14 F2."""

    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
