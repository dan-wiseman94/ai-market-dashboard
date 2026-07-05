"""Calibration-drift detection: recent vs baseline EvalRun.calibration_error."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.analytics.models import EvalRun
from apps.analytics.services.calibration_drift import calibration_drift

NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _run(model: str, *, days_ago: int, cal_error: float, hit=0.6, conf=0.6) -> None:
    run = EvalRun.objects.create(
        model=model, scored=10, n=10, hit_rate=hit, avg_confidence=conf, calibration_error=cal_error
    )
    EvalRun.objects.filter(pk=run.pk).update(created_at=NOW - timedelta(days=days_ago))


def _model_row(result: dict, model: str) -> dict:
    return next(m for m in result["models"] if m["model"] == model)


@pytest.mark.django_db
def test_drift_flagged_when_error_worsens():
    # baseline window (days 30-60 ago) error ~0.05; recent (0-30) ~0.20 → drifting.
    for d in (35, 45, 55):
        _run("opus", days_ago=d, cal_error=0.05)
    for d in (5, 15, 25):
        _run("opus", days_ago=d, cal_error=0.20, conf=0.85, hit=0.55)
    row = _model_row(calibration_drift(now=NOW), "opus")
    assert row["drifting"] is True
    assert row["baseline_error"] == pytest.approx(0.05)
    assert row["recent_error"] == pytest.approx(0.20)
    assert row["direction"] == "overconfident"  # conf 0.85 >> hit 0.55


@pytest.mark.django_db
def test_no_drift_when_stable():
    for d in (35, 45, 55):
        _run("sonnet", days_ago=d, cal_error=0.10)
    for d in (5, 15, 25):
        _run("sonnet", days_ago=d, cal_error=0.11)  # +0.01 only
    row = _model_row(calibration_drift(now=NOW), "sonnet")
    assert row["drifting"] is False
    assert row["status"] == "scored"


@pytest.mark.django_db
def test_insufficient_history_below_min_runs():
    for d in (35, 45, 55):
        _run("haiku", days_ago=d, cal_error=0.05)
    _run("haiku", days_ago=5, cal_error=0.30)  # only ONE recent run
    row = _model_row(calibration_drift(now=NOW, min_runs=3), "haiku")
    assert row["status"] == "insufficient_history"
    assert row["drifting"] is False


@pytest.mark.django_db
def test_underconfident_direction():
    for d in (35, 45, 55):
        _run("u", days_ago=d, cal_error=0.05)
    for d in (5, 15, 25):
        _run("u", days_ago=d, cal_error=0.20, conf=0.40, hit=0.70)
    row = _model_row(calibration_drift(now=NOW), "u")
    assert row["direction"] == "underconfident"  # conf 0.40 << hit 0.70


# ---------------------------------------------------------------------------
# Sentinel beat task — opt-in, fires once per drift episode, re-arms on recovery
# ---------------------------------------------------------------------------


def _drifting_runs(model="opus", *, recent_err=0.20):
    from django.utils import timezone

    now = timezone.now()
    for d in (35, 45, 55):
        run = EvalRun.objects.create(
            model=model, scored=10, n=10, hit_rate=0.55, avg_confidence=0.85, calibration_error=0.05
        )
        EvalRun.objects.filter(pk=run.pk).update(created_at=now - timedelta(days=d))
    for d in (5, 15, 25):
        run = EvalRun.objects.create(
            model=model,
            scored=10,
            n=10,
            hit_rate=0.55,
            avg_confidence=0.85,
            calibration_error=recent_err,
        )
        EvalRun.objects.filter(pk=run.pk).update(created_at=now - timedelta(days=d))


@pytest.mark.django_db
def test_sentinel_fires_once_then_dedups(monkeypatch, settings):
    import fakeredis

    from apps.analytics import tasks
    from apps.observer.models import Notification

    settings.CALIBRATION_DRIFT_SENTINEL_ENABLED = True
    fake = fakeredis.FakeStrictRedis()  # one instance — the dedup marker must persist across calls
    monkeypatch.setattr(tasks, "_redis", lambda: fake)

    _drifting_runs("opus")
    r1 = tasks.calibration_drift_sentinel()
    assert r1["fired"] == 1
    assert Notification.objects.filter(kind="cal_drift").count() == 1

    r2 = tasks.calibration_drift_sentinel()  # same drift → dedup, no new alert
    assert r2["fired"] == 0
    assert Notification.objects.filter(kind="cal_drift").count() == 1


@pytest.mark.django_db
def test_sentinel_disabled_is_noop(settings):
    from apps.analytics import tasks

    settings.CALIBRATION_DRIFT_SENTINEL_ENABLED = False
    assert tasks.calibration_drift_sentinel() == {"skipped": "disabled"}


@pytest.mark.django_db
def test_calibration_drift_endpoint_200():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/analytics/calibration-drift/")
    assert resp.status_code == 200
    body = resp.json()
    assert "models" in body and "window_days" in body
