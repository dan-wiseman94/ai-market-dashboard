"""Lesson visibility — the single rule for which distilled lessons reach the Coach.

Shared by the coach's distilled-lessons block (``apps.threads.coach``) and the
lessons API, so the two cannot disagree about what the user is actually looking
at: a lesson reaches the coach when it is not muted AND either pinned or backed
by at least ``MIN_LESSON_SUPPORT`` post-mortems.

``support_n`` is recomputed by the distiller from a lesson's evidence rows, so a
hand-written lesson sits at 0 forever; ``pinned`` is the escape hatch that makes
one visible.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

# A distilled lesson must recur across at least this many post-mortems to count
# as a pattern worth putting in front of the model.
MIN_LESSON_SUPPORT = 2

# Predicate form of the same rule, as an ORM filter.
COACH_VISIBLE = Q(muted=False) & (Q(pinned=True) | Q(support_n__gte=MIN_LESSON_SUPPORT))


def coach_visible_lessons() -> QuerySet:
    """Lessons the coach may surface, pinned first then best-supported."""
    from apps.thesis.models import Lesson

    return Lesson.objects.filter(COACH_VISIBLE).order_by("-pinned", "-support_n", "-last_seen")


def is_coach_visible(lesson) -> bool:
    """Row-level form of :data:`COACH_VISIBLE`, for serializing one lesson."""
    return not lesson.muted and (lesson.pinned or lesson.support_n >= MIN_LESSON_SUPPORT)
