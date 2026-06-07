"""Tests for the surviving persona prompt helpers (_FRAMING / _user_prompt).

The debate path (services/debate.py) consumes these; the superseded
run_structured-based run_persona was removed."""

from apps.strategy.warroom.services import personas as P


def test_user_prompt_includes_subject_and_observational_directive():
    out = P._user_prompt("subject ctx", [])
    assert "subject ctx" in out
    assert "observational" in out.lower()


def test_user_prompt_includes_prior_args_for_rebuttal():
    out = P._user_prompt("ctx", [{"persona": "bull", "argument": "bull says up"}])
    assert "bull says up" in out
    assert "rebut" in out.lower()


def test_framing_covers_each_persona():
    assert set(P._FRAMING) == {"bull", "bear", "skeptic"}
