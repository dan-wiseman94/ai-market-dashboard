from typing import ClassVar

import pytest

from apps.warroom.services import personas as P

pytestmark = pytest.mark.django_db


def test_run_persona_calls_run_structured(monkeypatch):
    captured = {}

    class _Arg:
        argument = "Bull case: AI capex durable."
        key_points: ClassVar = ["capex", "moat"]

    def _fake(**kw):
        captured.update(kw)
        return _Arg()

    monkeypatch.setattr(P, "run_structured", _fake)
    out = P.run_persona(
        "bull", "subject ctx", [], api_key="k", model="claude-opus-4-8", base_url=""
    )
    assert out.argument.startswith("Bull")
    assert "BULL" in captured["system"].upper()
    assert "subject ctx" in captured["user"]


def test_rebuttal_includes_prior(monkeypatch):
    class _Arg:
        argument = "x"
        key_points: ClassVar = []

    cap = {}
    monkeypatch.setattr(P, "run_structured", lambda **kw: cap.update(kw) or _Arg())
    P.run_persona(
        "bear",
        "ctx",
        [{"persona": "bull", "argument": "bull says up"}],
        api_key="k",
        model="m",
        base_url="",
    )
    assert "bull says up" in cap["user"]
