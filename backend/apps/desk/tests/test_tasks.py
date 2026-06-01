import pytest
from django.test import override_settings

from apps.desk import tasks

pytestmark = pytest.mark.django_db


@override_settings(ANOMALY_SWEEP_ENABLED=False)
def test_sweep_disabled_by_default(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "run_sweep", lambda **k: calls.append(1))
    assert tasks.sweep.run() is None
    assert calls == []


@override_settings(ANOMALY_SWEEP_ENABLED=True)
def test_sweep_runs_when_enabled(monkeypatch):
    monkeypatch.setattr(tasks, "run_sweep", lambda **k: 2)
    assert tasks.sweep.run() == 2
