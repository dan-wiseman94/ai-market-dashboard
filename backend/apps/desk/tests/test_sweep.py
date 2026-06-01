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
