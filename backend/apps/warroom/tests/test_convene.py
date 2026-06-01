import pytest

from apps.threads.models import Message
from apps.warroom.models import WarRoomRun
from apps.warroom.services import convene as CV

pytestmark = pytest.mark.django_db


def _patch_ai(monkeypatch):
    class _Arg:
        def __init__(self, p):
            self.argument = f"{p} argument"
            self.key_points = [p]

    class _V:
        verdict = "balanced"
        confidence = 0.5
        strongest_bull = "b"
        strongest_bear = "r"
        what_would_change_my_mind = "x"

    monkeypatch.setattr(CV, "run_persona", lambda persona, *a, **k: _Arg(persona))
    monkeypatch.setattr(CV, "synthesize", lambda *a, **k: _V())
    monkeypatch.setattr(CV, "_claude_cfg", lambda: ("key", "claude-opus-4-8", ""))


def test_convene_free_prompt_judge_panel(monkeypatch):
    _patch_ai(monkeypatch)
    run = CV.convene(free_prompt="NVDA into earnings?", structure="judge_panel")
    assert run.status == "done"
    assert run.verdict["verdict"] == "balanced"
    assert run.confidence == 0.5
    th = run.thread
    assert th.kind == "warroom"
    roles = list(Message.objects.filter(thread=th).values_list("role", flat=True))
    assert roles.count("assistant") == 4  # 3 personas + verdict
    assert Message.objects.filter(thread=th, content__kind="warroom_verdict").exists()


def test_convene_rebuttal_runs_two_rounds(monkeypatch):
    calls = []
    _patch_ai(monkeypatch)
    monkeypatch.setattr(
        CV,
        "run_persona",
        lambda persona, ctx, prior, **k: (
            calls.append((persona, len(prior)))
            or type("A", (), {"argument": persona, "key_points": []})()
        ),
    )
    CV.convene(free_prompt="q", structure="rebuttal")
    assert any(n == 0 for _p, n in calls) and any(n > 0 for _p, n in calls)


def test_convene_no_key_returns_error(monkeypatch):
    monkeypatch.setattr(CV, "_claude_cfg", lambda: None)
    run = CV.convene(free_prompt="q")
    assert run.status == "error"
    assert WarRoomRun.objects.filter(status="error").exists()
