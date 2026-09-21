"""The /api/lessons/ review surface: list, author, edit, mute, pin, prune.

The load-bearing property is that what this endpoint reports as
``visible_to_coach`` is exactly what the coach's distilled-lessons block surfaces
— a hand-written lesson that the coach silently drops is the defect these cover.
"""

import pytest
from rest_framework.test import APIClient

from apps.thesis.lessons import MIN_LESSON_SUPPORT
from apps.thesis.models import Lesson


def _items(resp):
    data = resp.json()
    return data["results"] if isinstance(data, dict) and "results" in data else data


@pytest.mark.django_db
def test_list_mute_and_prune():
    client = APIClient()
    lesson = Lesson.objects.create(
        text="lesson one", tags={"directions": ["bearish"]}, support_n=3, embedding=[0.1, 0.2]
    )

    resp = client.get("/api/lessons/")
    assert resp.status_code == 200
    items = _items(resp)
    assert any(it["text"] == "lesson one" for it in items)
    assert "embedding" not in items[0]  # the vector is never exposed
    assert items[0]["visible_to_coach"] is True

    resp = client.patch(f"/api/lessons/{lesson.id}/", {"muted": True}, format="json")
    assert resp.status_code == 200
    assert resp.json()["visible_to_coach"] is False
    lesson.refresh_from_db()
    assert lesson.muted is True

    resp = client.delete(f"/api/lessons/{lesson.id}/")
    assert resp.status_code == 204
    assert Lesson.objects.count() == 0


@pytest.mark.django_db
def test_create_authors_a_pinned_lesson():
    resp = APIClient().post(
        "/api/lessons/",
        {"text": "  Size down into earnings  ", "tags": {"directions": ["bullish"]}},
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["text"] == "Size down into earnings"
    # No evidence rows, so support_n stays below the threshold — `pinned` is what
    # keeps the lesson reachable.
    assert body["support_n"] == 0 < MIN_LESSON_SUPPORT
    assert body["pinned"] is True
    assert body["visible_to_coach"] is True


@pytest.mark.django_db
def test_create_rejects_an_untaggable_lesson():
    client = APIClient()
    resp = client.post("/api/lessons/", {"text": "no tags"}, format="json")
    assert resp.status_code == 400
    assert "tags" in resp.json()

    resp = client.post(
        "/api/lessons/", {"text": "bad direction", "tags": {"directions": ["long"]}}, format="json"
    )
    assert resp.status_code == 400
    assert Lesson.objects.count() == 0


@pytest.mark.django_db
def test_create_normalizes_tags():
    resp = APIClient().post(
        "/api/lessons/",
        {"text": "t", "tags": {"sectors": [" Energy ", "Energy", ""], "extra": "dropped"}},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["tags"] == {"directions": [], "sectors": ["Energy"]}


@pytest.mark.django_db
def test_list_filters_by_pinned_muted_and_visibility():
    client = APIClient()
    pinned = Lesson.objects.create(text="pinned", tags={"directions": ["bullish"]}, pinned=True)
    thin = Lesson.objects.create(text="thin", tags={"directions": ["bullish"]}, support_n=1)
    Lesson.objects.create(text="muted", tags={"directions": ["bullish"]}, support_n=9, muted=True)

    assert {it["id"] for it in _items(client.get("/api/lessons/?visible=true"))} == {pinned.id}
    assert thin.id in {it["id"] for it in _items(client.get("/api/lessons/?visible=false"))}
    assert {it["id"] for it in _items(client.get("/api/lessons/?pinned=true"))} == {pinned.id}
    assert {it["id"] for it in _items(client.get("/api/lessons/?muted=false"))} == {
        pinned.id,
        thin.id,
    }


@pytest.mark.django_db
def test_hand_written_lesson_reaches_the_coach():
    """The whole point of `pinned`: an authored lesson has support_n == 0, which the
    coach's support threshold would otherwise filter out permanently."""
    from apps.thesis.models import Thesis
    from apps.threads.coach import _distilled_lessons_block

    Thesis.objects.create(title="t", ticker="NVDA", direction="bearish", status="open")
    resp = APIClient().post(
        "/api/lessons/",
        {"text": "You chase gaps", "tags": {"directions": ["bearish"]}},
        format="json",
    )
    assert resp.status_code == 201

    block = _distilled_lessons_block("NVDA")
    assert "You chase gaps" in block
    assert "0 past calls" not in block  # provenance reads as the trader's own rule


@pytest.mark.django_db
def test_unpinning_an_authored_lesson_hides_it_from_the_coach():
    from apps.thesis.models import Thesis
    from apps.threads.coach import _distilled_lessons_block

    Thesis.objects.create(title="t", ticker="NVDA", direction="bearish", status="open")
    lesson = Lesson.objects.create(
        text="You chase gaps", tags={"directions": ["bearish"]}, pinned=True
    )

    resp = APIClient().patch(f"/api/lessons/{lesson.id}/", {"pinned": False}, format="json")
    assert resp.status_code == 200
    assert resp.json()["visible_to_coach"] is False
    assert _distilled_lessons_block("NVDA") == ""
