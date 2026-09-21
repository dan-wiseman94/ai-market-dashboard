"""Distilled-lessons API (``/api/lessons/``) — the review surface over the Coach's
recurring-lesson memory: list, author, edit, mute, pin, prune.

Authoring a lesson by hand is a first-class path: the distiller only ever produces
lessons the post-mortems happened to cluster, and a trader's own standing rule has
no evidence rows behind it. Such a lesson is created ``pinned`` because ``support_n``
stays 0 and the coach's support threshold would otherwise hide it forever.
"""

from typing import ClassVar

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets

from apps.thesis.lessons import COACH_VISIBLE, is_coach_visible
from apps.thesis.models import Lesson, Thesis

_DIRECTIONS = sorted(d for d, _ in Thesis.DIRECTION_CHOICES)
_TAG_KEYS = ("directions", "sectors")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _flag(raw: str | None) -> bool | None:
    """Tri-state query-param boolean: True / False / None (param absent or junk)."""
    value = (raw or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None


class LessonSerializer(serializers.ModelSerializer):
    # The coach's visibility rule, resolved server-side so the review UI shows what
    # is actually reaching the model rather than re-deriving the threshold.
    visible_to_coach = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        # embedding (the 384-float vector) is deliberately not exposed.
        fields: ClassVar = [
            "id",
            "text",
            "tags",
            "support_n",
            "muted",
            "pinned",
            "visible_to_coach",
            "last_seen",
            "created_at",
            "updated_at",
        ]
        # support_n / last_seen are the distiller's bookkeeping, recomputed from the
        # evidence rows on every merge — writing them here would just be overwritten.
        read_only_fields: ClassVar = [
            "id",
            "support_n",
            "last_seen",
            "created_at",
            "updated_at",
        ]

    def get_visible_to_coach(self, obj: Lesson) -> bool:
        return is_coach_visible(obj)

    def validate_text(self, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("A lesson needs text.")
        return text

    def validate_tags(self, value: object) -> dict:
        """Normalize to ``{"directions": [...], "sectors": [...]}``.

        Tags are the coach's only matcher — it surfaces a lesson when the current
        situation's direction or sector is tagged on it — so a malformed or unknown
        direction is a lesson that silently never appears.
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                'tags must be an object, e.g. {"directions": ["bullish"], "sectors": ["Energy"]}.'
            )
        cleaned: dict[str, list[str]] = {}
        for key in _TAG_KEYS:
            raw = value.get(key, [])
            if not isinstance(raw, list):
                raise serializers.ValidationError(f"tags.{key} must be a list of strings.")
            cleaned[key] = sorted({str(x).strip() for x in raw if str(x).strip()})
        unknown = set(cleaned["directions"]) - set(_DIRECTIONS)
        if unknown:
            raise serializers.ValidationError(
                f"tags.directions must be drawn from {_DIRECTIONS}; got {sorted(unknown)}."
            )
        return cleaned

    def validate(self, attrs: dict) -> dict:
        """A lesson with no direction and no sector matches no situation — refuse it
        on create rather than storing something the coach can never surface."""
        if self.instance is None:
            tags = attrs.get("tags") or {}
            if not (tags.get("directions") or tags.get("sectors")):
                raise serializers.ValidationError(
                    {
                        "tags": (
                            "Tag the lesson with at least one direction "
                            f"({', '.join(_DIRECTIONS)}) or sector — the coach matches "
                            "on those, so an untagged lesson is never shown."
                        )
                    }
                )
        return attrs


def _flag_param(name: str, description: str) -> OpenApiParameter:
    """A tri-state filter: absent (or junk) means no filter at all, not False."""
    return OpenApiParameter(name, bool, description=description)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            _flag_param("muted", "Only muted lessons, or only unmuted ones."),
            _flag_param("pinned", "Only pinned lessons, or only unpinned ones."),
            _flag_param(
                "visible",
                "Filter on the resolved coach-visibility rule (the same rule the "
                "``visible_to_coach`` field reports), not on a stored column.",
            ),
        ]
    )
)
class LessonViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Author, review, mute/pin and prune the lessons the Coach draws on.

    List filters (all optional): ``?muted=``, ``?pinned=``, ``?visible=`` (the
    resolved coach-visibility rule). Ordering is pinned first, then best-supported.
    """

    serializer_class = LessonSerializer

    def get_queryset(self):
        qs = Lesson.objects.all().order_by("-pinned", "-support_n", "-last_seen")
        for field in ("muted", "pinned"):
            flag = _flag(self.request.query_params.get(field))
            if flag is not None:
                qs = qs.filter(**{field: flag})
        visible = _flag(self.request.query_params.get("visible"))
        if visible is True:
            qs = qs.filter(COACH_VISIBLE)
        elif visible is False:
            qs = qs.exclude(COACH_VISIBLE)
        return qs

    def perform_create(self, serializer) -> None:
        # No evidence rows means support_n == 0 and MIN_LESSON_SUPPORT never met, so a
        # hand-written lesson is authored pinned unless the caller opts out explicitly.
        serializer.save(pinned=serializer.validated_data.get("pinned", True))
