import pytest
from rest_framework.test import APIClient

from apps.strategy.models import WarRoomRun
from apps.strategy.warroom import views

pytestmark = pytest.mark.django_db


def test_convene_endpoint(monkeypatch):
    from apps.threads.models import Thread

    def _fake_convene(**kwargs):
        th = Thread.objects.create(kind="warroom", title="Debate: q")
        return WarRoomRun.objects.create(
            thread=th,
            subject_kind="free",
            subject_label="q",
            verdict={"verdict": "balanced"},
            confidence=0.5,
            status="done",
        )

    monkeypatch.setattr(views, "convene", _fake_convene)
    resp = APIClient().post(
        "/api/warroom/runs/convene/",
        {"free_prompt": "q", "structure": "judge_panel"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["verdict"]["verdict"] == "balanced"


def test_list_and_detail_runs():
    from apps.threads.models import Message, Thread

    th = Thread.objects.create(kind="warroom", title="t")
    Message.objects.create(
        thread=th, role="assistant", content={"persona": "bull", "argument": "a"}
    )
    run = WarRoomRun.objects.create(
        thread=th, subject_kind="free", subject_label="q", confidence=0.5
    )
    assert len(APIClient().get("/api/warroom/runs/").json()) == 1
    body = APIClient().get(f"/api/warroom/runs/{run.id}/").json()
    assert "messages" in body and len(body["messages"]) == 1
