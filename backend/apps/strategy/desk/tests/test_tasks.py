import pytest
from django.test import override_settings

from apps.strategy import tasks

pytestmark = pytest.mark.django_db


@override_settings(ANOMALY_SWEEP_ENABLED=False)
def test_sweep_is_a_noop_when_the_switch_is_off(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "run_sweep", lambda **k: calls.append(1))
    assert tasks.sweep.run() is None
    assert calls == []


@override_settings(ANOMALY_SWEEP_ENABLED=True)
def test_settings_switch_overrides_the_env_default(monkeypatch):
    """The Settings → Features switch reaches this task: a SystemSettings value
    beats the env default, and a NULL one inherits it."""
    from apps.core.models import SystemSettings

    calls = []
    monkeypatch.setattr(tasks, "run_sweep", lambda **k: calls.append(1) or 2)

    cfg = SystemSettings.load()
    cfg.anomaly_sweep_enabled = False
    cfg.save(update_fields=["anomaly_sweep_enabled"])
    assert tasks.sweep.run() is None
    assert calls == []

    cfg.anomaly_sweep_enabled = None
    cfg.save(update_fields=["anomaly_sweep_enabled"])
    assert tasks.sweep.run() == 2
