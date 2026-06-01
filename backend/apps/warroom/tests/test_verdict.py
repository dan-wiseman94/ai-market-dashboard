import pytest

from apps.warroom.services import verdict as V

pytestmark = pytest.mark.django_db


def test_synthesize_calls_run_structured(monkeypatch):
    class _V:
        verdict = "bull case stronger"
        confidence = 0.62
        strongest_bull = "capex"
        strongest_bear = "valuation"
        what_would_change_my_mind = "capex guidance cut"

    cap = {}
    monkeypatch.setattr(V, "run_structured", lambda **kw: cap.update(kw) or _V())
    out = V.synthesize("ctx", [{"persona": "bull", "argument": "a"}], api_key="k", model="m", base_url="")
    assert out.confidence == 0.62
    assert "bull" in cap["user"].lower()
