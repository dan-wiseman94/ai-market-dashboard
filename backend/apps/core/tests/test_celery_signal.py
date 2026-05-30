"""Tests for the Celery task_failure signal handler.

We test the handler function directly rather than relying on eager-mode
signal dispatch (which can be unreliable across Celery versions). This
gives deterministic coverage of:
  - an ErrorEvent is created with the correct source/message/level
  - task kwargs are NOT stored in detail (no secret leak)
  - the handler never raises even when ErrorEvent.record itself fails
"""

from __future__ import annotations

import pytest

from apps.core.models import ErrorEvent
from apps.core.signals import _on_task_failure


class _FakeSender:
    """Minimal stand-in for a Celery Task class."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeEInfo:
    def __str__(self) -> str:
        return "Traceback (most recent call last):\n  ...\nRuntimeError: Schwab token expired"


@pytest.mark.django_db
def test_handler_creates_error_event():
    """Calling the handler directly persists an ErrorEvent."""
    sender = _FakeSender("observer.run_observer")
    exc = RuntimeError("Schwab token expired")

    _on_task_failure(
        sender=sender,
        task_id="task-abc-123",
        exception=exc,
        traceback=None,
        einfo=_FakeEInfo(),
    )

    ev = ErrorEvent.objects.get(source="celery.task:observer.run_observer")
    assert ev.level == "error"
    assert ev.message == "RuntimeError: Schwab token expired"
    assert ev.fingerprint == "observer.run_observer"
    assert ev.detail["task_id"] == "task-abc-123"
    assert "Schwab token expired" in ev.detail["traceback"]
    assert ev.resolved is False


@pytest.mark.django_db
def test_handler_source_includes_task_name():
    """source field is prefixed 'celery.task:<name>'."""
    sender = _FakeSender("briefing.run_scheduled")
    exc = ConnectionError("Finnhub down")

    _on_task_failure(
        sender=sender,
        task_id="task-xyz",
        exception=exc,
        traceback=None,
        einfo=None,
    )

    ev = ErrorEvent.objects.get(source="celery.task:briefing.run_scheduled")
    assert ev.source == "celery.task:briefing.run_scheduled"
    assert ev.fingerprint == "briefing.run_scheduled"
    assert "ConnectionError" in ev.message


@pytest.mark.django_db
def test_handler_no_secret_leak_in_detail():
    """Task kwargs (which may hold API keys) must NOT appear in detail.

    We pass a fake secret value in kwargs and assert it is absent from
    the stored detail dict.
    """
    sender = _FakeSender("market.refresh_schwab_token")
    exc = ValueError("Bad credentials")

    # Simulate Celery passing task kwargs through **kw — handler must ignore them
    secret_value = "sk-SUPER_SECRET_API_KEY_12345"
    _on_task_failure(
        sender=sender,
        task_id="task-secret",
        exception=exc,
        traceback=None,
        einfo=None,
        kwargs={"api_key": secret_value, "bearer_token": "tok_HIDDEN"},
    )

    ev = ErrorEvent.objects.get(source="celery.task:market.refresh_schwab_token")
    detail_str = str(ev.detail)
    assert secret_value not in detail_str, "Secret API key must not be in stored detail"
    assert "tok_HIDDEN" not in detail_str, "Bearer token must not be in stored detail"
    # Only safe fields present
    assert "task_id" in ev.detail
    assert "traceback" in ev.detail


@pytest.mark.django_db
def test_handler_with_no_einfo_stores_empty_traceback():
    """When einfo is None, detail['traceback'] is empty string."""
    sender = _FakeSender("some.task")
    exc = OSError("disk full")

    _on_task_failure(
        sender=sender,
        task_id="task-no-einfo",
        exception=exc,
        traceback=None,
        einfo=None,
    )

    ev = ErrorEvent.objects.get(source="celery.task:some.task")
    assert ev.detail["traceback"] == ""


@pytest.mark.django_db
def test_handler_never_raises_on_record_failure(monkeypatch):
    """If ErrorEvent.record() itself raises, the handler must swallow it."""
    from apps.core import models as core_models

    def _boom(*args, **kwargs):
        raise RuntimeError("DB totally gone")

    monkeypatch.setattr(core_models.ErrorEvent, "record", staticmethod(_boom))

    sender = _FakeSender("some.failing.task")
    exc = Exception("whatever")

    # Must NOT raise — signal handlers must be bullet-proof
    _on_task_failure(
        sender=sender,
        task_id="task-boom",
        exception=exc,
        traceback=None,
        einfo=None,
    )
    # If we get here the handler swallowed the exception correctly
