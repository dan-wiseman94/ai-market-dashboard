import pytest
from django.test import override_settings

from apps.desk.models import DeskEntry
from apps.desk.services import sweep as S

pytestmark = pytest.mark.django_db


def _seed(monkeypatch, severity):
    monkeypatch.setattr(S, "build_universe", lambda: ["NVDA"])
    monkeypatch.setattr(S, "run_detectors", lambda uni: [{"anomaly_type": "price_move", "ticker": "NVDA", "severity": severity, "evidence": {}}])
    monkeypatch.setattr(S, "investigate", lambda cand: {"finding": "f", "suggested_actions": [{"type": "convene_warroom", "label": "x", "params": {"free_prompt": "p"}}], "investigation_thread_id": None})


@override_settings(AUTONOMY_AUTO_EXECUTE=False)
def test_no_autoexecute_by_default(monkeypatch):
    _seed(monkeypatch, 9.0)
    monkeypatch.setattr(S, "_auto_execute", lambda entry: (_ for _ in ()).throw(AssertionError("should not be called")))
    S.run_sweep(top_k=1)
    assert DeskEntry.objects.first().status == "new"


@override_settings(AUTONOMY_AUTO_EXECUTE=True)
def test_autoexecute_high_severity(monkeypatch):
    _seed(monkeypatch, 9.0)
    calls = []
    monkeypatch.setattr(S, "_auto_execute", lambda entry: calls.append(entry.id))
    S.run_sweep(top_k=1)
    assert len(calls) == 1


@override_settings(AUTONOMY_AUTO_EXECUTE=True)
def test_autoexecute_skips_low_severity(monkeypatch):
    _seed(monkeypatch, 2.0)
    calls = []
    monkeypatch.setattr(S, "_auto_execute", lambda entry: calls.append(entry.id))
    S.run_sweep(top_k=1)
    assert calls == []  # below AUTO_EXECUTE_MIN_SEVERITY
