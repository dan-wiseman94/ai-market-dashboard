import pytest

from apps.strategy.desk.services import investigate as I
from apps.threads.models import Message, Thread

pytestmark = pytest.mark.django_db

CAND = {
    "anomaly_type": "price_move",
    "ticker": "NVDA",
    "severity": 8.0,
    "evidence": {"pct_change": 8.0},
}


def test_no_assistant_message_returns_none(monkeypatch):
    # run_ai_on_message writes nothing (e.g. no provider) -> investigate returns None.
    monkeypatch.setattr(I, "run_ai_on_message", lambda **kw: {"status": "failed"})
    assert I.investigate(CAND) is None


def test_investigate_runs_bounded_investigation(monkeypatch):
    captured = {}

    def _fake_run(**kw):
        captured.update(kw)
        Message.objects.create(
            thread_id=kw["thread_id"],
            role="assistant",
            status="done",
            content={
                "text": "NVDA gapped on capex; breakout retest in play.",
                "kind": "investigation",
            },
        )
        return {"status": "done"}

    monkeypatch.setattr(I, "run_ai_on_message", _fake_run)
    out = I.investigate(CAND)
    assert out is not None
    assert "NVDA gapped" in out["finding"]
    assert captured["investigate"] is True
    th = Thread.objects.get(id=out["investigation_thread_id"])
    assert th.kind == "consult"
    assert Message.objects.filter(thread=th, role="user").exists()
    assert out["suggested_actions"][0]["type"] == "convene_warroom"
    # ticker anomalies also offer revise_coverage
    assert any(a["type"] == "revise_coverage" for a in out["suggested_actions"])


def _run_with_finding(text: str):
    def _fake_run(**kw):
        Message.objects.create(
            thread_id=kw["thread_id"], role="assistant", status="done", content={"text": text}
        )
        return {"status": "done"}

    return _fake_run


def test_investigate_offers_open_thesis_for_ticker(monkeypatch):
    monkeypatch.setattr(I, "run_ai_on_message", _run_with_finding("NVDA gapped up on capex."))
    out = I.investigate(CAND)  # price_move +8% on NVDA
    opens = [a for a in out["suggested_actions"] if a["type"] == "open_thesis"]
    assert len(opens) == 1
    params = opens[0]["params"]
    assert params["ticker"] == "NVDA"
    assert params["direction"] == "bullish"  # positive pct_change -> bullish
    assert "NVDA gapped" in params["rationale"]


def test_open_thesis_direction_follows_negative_move(monkeypatch):
    monkeypatch.setattr(I, "run_ai_on_message", _run_with_finding("NVDA broke down."))
    cand = {"anomaly_type": "price_move", "ticker": "NVDA", "evidence": {"pct_change": -8.0}}
    out = I.investigate(cand)
    opens = [a for a in out["suggested_actions"] if a["type"] == "open_thesis"]
    assert opens[0]["params"]["direction"] == "bearish"


def test_book_wide_finding_has_no_open_thesis(monkeypatch):
    monkeypatch.setattr(I, "run_ai_on_message", _run_with_finding("Regime flipped."))
    out = I.investigate({"anomaly_type": "regime_change", "ticker": "", "evidence": {}})
    assert not any(a["type"] == "open_thesis" for a in out["suggested_actions"])
