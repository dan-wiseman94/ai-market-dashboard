"""The coach-visibility rule has a queryset form and a row form; they must agree."""

import pytest

from apps.thesis.lessons import MIN_LESSON_SUPPORT, coach_visible_lessons, is_coach_visible
from apps.thesis.models import Lesson

CASES = [
    ("unsupported", 0, False, False),
    ("thin", MIN_LESSON_SUPPORT - 1, False, False),
    ("supported", MIN_LESSON_SUPPORT, False, False),
    ("pinned", 0, True, False),
    ("pinned and muted", 0, True, True),
    ("supported and muted", MIN_LESSON_SUPPORT, False, True),
]


@pytest.mark.django_db
def test_queryset_and_row_forms_agree():
    for text, support_n, pinned, muted in CASES:
        Lesson.objects.create(text=text, tags={}, support_n=support_n, pinned=pinned, muted=muted)

    visible = {lesson.id for lesson in coach_visible_lessons()}
    for lesson in Lesson.objects.all():
        assert is_coach_visible(lesson) is (lesson.id in visible), lesson.text


@pytest.mark.django_db
def test_pinned_lessons_sort_ahead_of_better_supported_ones():
    Lesson.objects.create(text="distilled", tags={}, support_n=9)
    Lesson.objects.create(text="authored", tags={}, pinned=True)
    assert [lesson.text for lesson in coach_visible_lessons()] == ["authored", "distilled"]
