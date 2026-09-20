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
            verdict={"verdict": "balanced", "confidence": 0.5},
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
    # confidence is now derived from verdict["confidence"] (no stored column).
    assert resp.json()["confidence"] == 0.5


def test_list_and_detail_runs():
    from apps.threads.models import Message, Thread

    th = Thread.objects.create(kind="warroom", title="t")
    Message.objects.create(
        thread=th, role="assistant", content={"persona": "bull", "argument": "a"}
    )
    run = WarRoomRun.objects.create(thread=th, subject_kind="free", subject_label="q")
    assert len(APIClient().get("/api/warroom/runs/").json()) == 1
    body = APIClient().get(f"/api/warroom/runs/{run.id}/").json()
    assert "messages" in body and len(body["messages"]) == 1


def test_run_messages_carry_the_provider_that_argued_them():
    """Each persona lane names its model; a message with no run reports nulls."""
    from decimal import Decimal

    from apps.threads.models import AIRun, Message, Thread

    th = Thread.objects.create(kind="warroom", title="t")
    argued = Message.objects.create(
        thread=th, role="assistant", content={"persona": "bull", "argument": "a"}
    )
    AIRun.objects.create(
        message=argued,
        provider="openai",
        model="gpt-5.6-sol",
        cost_usd=Decimal("0.01"),
        status="done",
    )
    Message.objects.create(thread=th, role="assistant", content={"kind": "warroom_verdict"})
    run = WarRoomRun.objects.create(thread=th, subject_kind="free", subject_label="q")

    messages = APIClient().get(f"/api/warroom/runs/{run.id}/").json()["messages"]
    assert messages[0]["provider"] == "openai"
    assert messages[0]["model"] == "gpt-5.6-sol"
    assert messages[1]["provider"] is None
    assert messages[1]["model"] is None
