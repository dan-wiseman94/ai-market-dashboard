import pytest
from rest_framework.test import APIClient

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

    resp = client.patch(f"/api/lessons/{lesson.id}/", {"muted": True}, format="json")
    assert resp.status_code == 200
    lesson.refresh_from_db()
    assert lesson.muted is True

    resp = client.delete(f"/api/lessons/{lesson.id}/")
    assert resp.status_code == 204
    assert Lesson.objects.count() == 0
