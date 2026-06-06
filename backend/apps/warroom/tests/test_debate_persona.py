import pytest

from apps.threads.models import Message, Thread
from apps.warroom.services import debate as D

pytestmark = pytest.mark.django_db


def test_run_one_persona_dispatches_and_stamps(monkeypatch):
    th = Thread.objects.create(kind="warroom", title="t")
    captured = {}

    def _fake_run(**kw):
        captured.update(kw)
        Message.objects.create(
            thread_id=kw["thread_id"],
            role="assistant",
            status="done",
            content={"text": "bull case", "kind": "investigation"},
        )
        return {"status": "done"}

    monkeypatch.setattr(D, "run_ai_on_message", _fake_run)
    arg = D.run_one_persona(
        th, "bull", "SUBJECT ctx", [], provider="claude", model="claude-opus-4-8", grounding=True
    )
    assert arg["persona"] == "bull"
    assert "bull case" in arg["argument"]
    assert captured["override"] == {"provider": "claude", "model": "claude-opus-4-8"}
    assert captured["investigate"] is True
    msg = Message.objects.filter(thread=th, role="assistant").latest("created_at")
    assert msg.content["persona"] == "bull"


def test_run_one_persona_none_when_no_assistant(monkeypatch):
    th = Thread.objects.create(kind="warroom", title="t")
    monkeypatch.setattr(D, "run_ai_on_message", lambda **kw: {"status": "failed"})
    assert (
        D.run_one_persona(th, "bear", "ctx", [], provider="claude", model="m", grounding=False)
        is None
    )


def test_run_one_persona_does_not_inherit_a_prior_personas_message(monkeypatch):
    """Personas run sequentially in one shared thread. If THIS persona's run fails or
    no-ops, it must return None — not pick up the *previous* persona's assistant
    message and re-stamp it (which the courtroom UI would then mislabel)."""
    th = Thread.objects.create(kind="warroom", title="t")
    # A prior persona's successful argument already sits in the thread.
    prior = Message.objects.create(
        thread=th,
        role="assistant",
        status="done",
        content={"text": "BULL ARGUMENT", "persona": "bull"},
    )
    # This persona's run produces no new "done" assistant message.
    monkeypatch.setattr(D, "run_ai_on_message", lambda **kw: {"status": "failed"})

    result = D.run_one_persona(th, "bear", "ctx", [], provider="claude", model="m", grounding=False)

    assert result is None
    prior.refresh_from_db()
    assert prior.content["persona"] == "bull"  # NOT re-stamped as "bear"
