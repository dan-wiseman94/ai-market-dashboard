import pytest

from apps.threads.models import Message, Thread
from apps.warroom.services import debate as D

pytestmark = pytest.mark.django_db


def test_run_one_persona_dispatches_and_stamps(monkeypatch):
    th = Thread.objects.create(kind="warroom", title="t")
    captured = {}

    def _fake_run(**kw):
        captured.update(kw)
        Message.objects.create(thread_id=kw["thread_id"], role="assistant", status="done",
                               content={"text": "bull case", "kind": "investigation"})
        return {"status": "done"}

    monkeypatch.setattr(D, "run_ai_on_message", _fake_run)
    arg = D.run_one_persona(th, "bull", "SUBJECT ctx", [], provider="claude", model="claude-opus-4-8", grounding=True)
    assert arg["persona"] == "bull"
    assert "bull case" in arg["argument"]
    assert captured["override"] == {"provider": "claude", "model": "claude-opus-4-8"}
    assert captured["investigate"] is True
    msg = Message.objects.filter(thread=th, role="assistant").latest("created_at")
    assert msg.content["persona"] == "bull"


def test_run_one_persona_none_when_no_assistant(monkeypatch):
    th = Thread.objects.create(kind="warroom", title="t")
    monkeypatch.setattr(D, "run_ai_on_message", lambda **kw: {"status": "failed"})
    assert D.run_one_persona(th, "bear", "ctx", [], provider="claude", model="m", grounding=False) is None
