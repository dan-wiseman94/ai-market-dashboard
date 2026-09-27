"""Tests for ErrorEvent model and record() helper."""

from __future__ import annotations

import pytest

from apps.core.models import ErrorEvent


@pytest.mark.django_db
def test_record_never_raises_on_inner_failure(monkeypatch):
    """If the inner create() call raises, record() returns None without propagating."""

    def _boom(*args, **kwargs):
        raise RuntimeError("DB is gone")

    monkeypatch.setattr(ErrorEvent.objects.__class__, "create", _boom)

    result = ErrorEvent.record(level="error", source="test", message="test")
    assert result is None
