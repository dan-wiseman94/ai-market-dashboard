import pytest

from apps.desk.models import DeskEntry
from apps.desk.services import sweep as S

pytestmark = pytest.mark.django_db


def test_sweep_creates_entries_for_top_k(monkeypatch):
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA", "AMD"])
    monkeypatch.setattr(
        S,
        "run_detectors",
        lambda uni: [
            {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}},
            {"anomaly_type": "price_move", "ticker": "AMD", "severity": 1.0, "evidence": {}},
        ],
    )
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": []})
    n = S.run_sweep(top_k=1)
    assert n == 1
    assert DeskEntry.objects.count() == 1
    assert DeskEntry.objects.first().ticker == "NVDA"


def test_sweep_respects_cooldown(monkeypatch):
    DeskEntry.objects.create(anomaly_type="price_move", ticker="NVDA", severity=9.0)
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA"])
    monkeypatch.setattr(
        S,
        "run_detectors",
        lambda uni: [
            {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}}
        ],
    )
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": []})
    n = S.run_sweep(top_k=3)
    assert n == 0


def test_sweep_enforces_daily_origination_cap(monkeypatch):
    from apps.desk import constants as C

    monkeypatch.setattr(C, "DAILY_ORIGINATION_CAP", 2)
    # One origination already happened today.
    DeskEntry.objects.create(anomaly_type="price_move", ticker="OLD", severity=1.0)
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA", "AMD", "TSLA"])
    monkeypatch.setattr(
        S,
        "run_detectors",
        lambda uni: [
            {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}},
            {"anomaly_type": "price_move", "ticker": "AMD", "severity": 8.0, "evidence": {}},
            {"anomaly_type": "price_move", "ticker": "TSLA", "severity": 7.0, "evidence": {}},
        ],
    )
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": []})
    # top_k is generous so the daily cap is the binding constraint.
    n = S.run_sweep(top_k=10)
    assert n == 1  # cap=2, one already today -> only 1 more may originate
    assert DeskEntry.objects.count() == 2


def test_sweep_links_investigation_thread(monkeypatch):
    from apps.threads.models import Thread

    th = Thread.objects.create(kind="consult", title="t")
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA"])
    monkeypatch.setattr(
        S,
        "run_detectors",
        lambda uni: [
            {"anomaly_type": "price_move", "ticker": "NVDA", "severity": 9.0, "evidence": {}}
        ],
    )
    monkeypatch.setattr(
        S,
        "investigate",
        lambda cand: {"finding": "f", "suggested_actions": [], "investigation_thread_id": th.id},
    )
    S.run_sweep(top_k=1)
    from apps.desk.models import DeskEntry

    assert DeskEntry.objects.first().investigation_thread_id == th.id
