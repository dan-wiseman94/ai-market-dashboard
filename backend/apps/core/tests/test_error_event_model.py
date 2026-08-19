"""Tests for ErrorEvent model and record() helper."""

from __future__ import annotations

import pytest

from apps.core.models import ErrorEvent


@pytest.mark.django_db
def test_error_event_create_stores_all_fields():
    """Direct .objects.create stores every field correctly."""
    ev = ErrorEvent.objects.create(
        level="warning",
        source="celery.task:market.refresh_schwab_token",
        message="TokenExpiredError: token is stale",
        detail={"task_id": "abc-123", "traceback": "Traceback ..."},
        fingerprint="market.refresh_schwab_token",
    )
    assert ev.pk is not None
    assert ev.level == "warning"
    assert ev.source == "celery.task:market.refresh_schwab_token"
    assert ev.message == "TokenExpiredError: token is stale"
    assert ev.detail == {"task_id": "abc-123", "traceback": "Traceback ..."}
    assert ev.fingerprint == "market.refresh_schwab_token"
    assert ev.resolved is False
    assert ev.created_at is not None


@pytest.mark.django_db
def test_error_event_defaults():
    """level defaults to 'error', resolved defaults to False, fingerprint defaults to ''."""
    ev = ErrorEvent.objects.create(source="test.source", message="boom")
    assert ev.level == "error"
    assert ev.resolved is False
    assert ev.fingerprint == ""
    assert ev.detail == {}


@pytest.mark.django_db
def test_record_creates_and_returns_event():
    """ErrorEvent.record() creates a DB row and returns it."""
    ev = ErrorEvent.record(
        level="error",
        source="celery.task:observer.run_observer",
        message="RuntimeError: Schwab token expired",
        detail={"task_id": "xyz", "traceback": "..."},
        fingerprint="observer.run_observer",
    )
    assert ev is not None
    assert ev.pk is not None
    assert ErrorEvent.objects.filter(pk=ev.pk).exists()
    assert ev.level == "error"
    assert ev.source == "celery.task:observer.run_observer"
    assert ev.message == "RuntimeError: Schwab token expired"
    assert ev.fingerprint == "observer.run_observer"
    assert ev.resolved is False


@pytest.mark.django_db
def test_record_with_no_detail_defaults_to_empty_dict():
    """record() without detail= stores {} not None."""
    ev = ErrorEvent.record(level="error", source="s", message="m")
    assert ev is not None
    assert ev.detail == {}


@pytest.mark.django_db
def test_record_never_raises_on_inner_failure(monkeypatch):
    """If the inner create() call raises, record() returns None without propagating."""

    def _boom(*args, **kwargs):
        raise RuntimeError("DB is gone")

    monkeypatch.setattr(ErrorEvent.objects.__class__, "create", _boom)

    result = ErrorEvent.record(level="error", source="test", message="test")
    assert result is None
