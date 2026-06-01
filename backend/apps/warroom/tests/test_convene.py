import pytest
from django.test import override_settings

from apps.threads.models import Message
from apps.warroom.models import WarRoomRun
from apps.warroom.services import convene as CV
from apps.warroom import tasks as T

pytestmark = pytest.mark.django_db


def _patch(monkeypatch):
    monkeypatch.setattr(
        T,
        "assign_voices",
        lambda mode: [(p, "claude", "claude-opus-4-8") for p in ("bull", "bear", "skeptic")],
    )
    monkeypatch.setattr(
        T,
        "run_one_persona",
        lambda thread, persona, ctx, prior, **kw: {
            "persona": persona,
            "argument": f"{persona} arg",
        },
    )

    class _V:
        verdict = "balanced"
        confidence = 0.5
        strongest_bull = "b"
        strongest_bear = "r"
        what_would_change_my_mind = "x"

    monkeypatch.setattr(T, "synthesize", lambda ctx, args, **kw: _V())
    monkeypatch.setattr(T, "_claude_cfg", lambda: ("k", "claude-opus-4-8", ""))


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_convene_creates_run_and_dispatches_to_done(monkeypatch):
    _patch(monkeypatch)
    run = CV.convene(free_prompt="NVDA?", structure="judge_panel", voice_mode="single")
    assert run.thread.kind == "warroom"
    run.refresh_from_db()  # CELERY eager -> run_debate already executed
    assert run.status == "done"
    assert run.verdict["verdict"] == "balanced"
    assert Message.objects.filter(thread=run.thread, content__kind="warroom_verdict").exists()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_convene_no_provider_errors(monkeypatch):
    monkeypatch.setattr(T, "_claude_cfg", lambda: None)
    monkeypatch.setattr(
        T, "assign_voices", lambda mode: [(p, "", "") for p in ("bull", "bear", "skeptic")]
    )
    run = CV.convene(free_prompt="q")
    run.refresh_from_db()
    assert run.status == "error"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_rebuttal_runs_extra_round(monkeypatch):
    _patch(monkeypatch)
    calls = []
    monkeypatch.setattr(
        T,
        "run_one_persona",
        lambda thread, persona, ctx, prior, **kw: (
            calls.append((persona, len(prior))) or {"persona": persona, "argument": "a"}
        ),
    )
    CV.convene(free_prompt="q", structure="rebuttal")
    assert any(n == 0 for _p, n in calls) and any(n > 0 for _p, n in calls)
