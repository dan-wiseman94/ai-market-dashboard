import pytest

from apps.regime import tasks

pytestmark = pytest.mark.django_db


def test_refresh_skips_when_market_closed(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks, "is_market_open", lambda: False)
    monkeypatch.setattr(tasks, "compute_and_store", lambda: calls.append(1))
    assert tasks.refresh.run() is None
    assert calls == []


def test_refresh_runs_when_open(monkeypatch):
    calls = []

    class _R:
        id = 7

    monkeypatch.setattr(tasks, "is_market_open", lambda: True)
    monkeypatch.setattr(tasks, "compute_and_store", lambda: (calls.append(1), _R())[1])
    assert tasks.refresh.run() == 7
    assert len(calls) == 1


def test_refresh_force_runs_when_closed(monkeypatch):
    calls = []

    class _R:
        id = 9

    monkeypatch.setattr(tasks, "is_market_open", lambda: False)
    monkeypatch.setattr(tasks, "compute_and_store", lambda: (calls.append(1), _R())[1])
    assert tasks.refresh.run(force=True) == 9
    assert len(calls) == 1
