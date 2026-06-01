import pytest
from rest_framework.test import APIClient

from apps.warroom import views

pytestmark = pytest.mark.django_db


def test_convene_forwards_voice_and_grounding(monkeypatch):
    captured = {}

    def _fake(**kw):
        captured.update(kw)
        from apps.threads.models import Thread
        from apps.warroom.models import WarRoomRun
        th = Thread.objects.create(kind="warroom", title="t")
        return WarRoomRun.objects.create(thread=th, subject_kind="free", subject_label="q", status="running")

    monkeypatch.setattr(views, "convene", _fake)
    resp = APIClient().post("/api/warroom/runs/convene/",
                            {"free_prompt": "q", "voice_mode": "multi", "grounding": True}, format="json")
    assert resp.status_code == 200
    assert captured["voice_mode"] == "multi"
    assert captured["grounding"] is True
    assert resp.json()["status"] == "running"


def test_convene_grounded_by_default(monkeypatch):
    captured = {}

    def _fake(**kw):
        captured.update(kw)
        from apps.threads.models import Thread
        from apps.warroom.models import WarRoomRun
        th = Thread.objects.create(kind="warroom", title="t")
        return WarRoomRun.objects.create(thread=th, subject_kind="free", subject_label="q", status="running")

    monkeypatch.setattr(views, "convene", _fake)
    APIClient().post("/api/warroom/runs/convene/", {"free_prompt": "q"}, format="json")
    assert captured["grounding"] is True  # v2 default: grounded
