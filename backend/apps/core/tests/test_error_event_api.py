"""Tests for GET /api/errors/ and POST /api/errors/<id>/resolve/."""

from __future__ import annotations

import pytest
from django.test import Client

from apps.core.models import ErrorEvent


def _make_event(**kwargs) -> ErrorEvent:
    defaults = {
        "level": "error",
        "source": "celery.task:some.task",
        "message": "boom",
        "fingerprint": "some.task",
    }
    defaults.update(kwargs)
    return ErrorEvent.objects.create(**defaults)


@pytest.mark.django_db
def test_get_errors_returns_newest_first():
    """Results are ordered newest → oldest."""
    client = Client()
    import time

    e1 = _make_event(source="task.a", message="first")
    time.sleep(0.01)
    e2 = _make_event(source="task.b", message="second")
    time.sleep(0.01)
    e3 = _make_event(source="task.c", message="third")

    resp = client.get("/api/errors/")
    assert resp.status_code == 200
    body = resp.json()
    ids = [e["id"] for e in body["results"]]
    assert ids.index(e3.pk) < ids.index(e2.pk) < ids.index(e1.pk), (
        "Events must be ordered newest-first"
    )


@pytest.mark.django_db
def test_get_errors_response_shape():
    """Response includes required fields per the spec."""
    client = Client()
    ev = _make_event(
        level="warning",
        source="celery.task:observer.run",
        message="msg",
        fingerprint="observer.run",
    )

    resp = client.get("/api/errors/")
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "count" in body
    assert body["count"] >= 1

    row = next(e for e in body["results"] if e["id"] == ev.pk)
    assert row["level"] == "warning"
    assert row["source"] == "celery.task:observer.run"
    assert row["message"] == "msg"
    assert row["fingerprint"] == "observer.run"
    assert row["resolved"] is False
    assert "created_at" in row
    # detail is excluded from list view (spec only says id/level/source/message/fingerprint/resolved/created_at)


@pytest.mark.django_db
def test_get_errors_unresolved_filter():
    """?unresolved=true returns only unresolved events."""
    client = Client()
    unresolved = _make_event(source="task.unresolved", resolved=False)
    resolved = _make_event(source="task.resolved", resolved=True)

    resp = client.get("/api/errors/?unresolved=true")
    assert resp.status_code == 200
    body = resp.json()
    ids = [e["id"] for e in body["results"]]
    assert unresolved.pk in ids
    assert resolved.pk not in ids


@pytest.mark.django_db
def test_get_errors_unresolved_false_returns_all():
    """?unresolved=false (or absent) returns all events including resolved."""
    client = Client()
    _make_event(source="task.unresolved", resolved=False)
    _make_event(source="task.resolved", resolved=True)

    resp = client.get("/api/errors/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 2


@pytest.mark.django_db
def test_get_errors_limit_cap():
    """?limit= is respected; default is 50, max is 200."""
    client = Client()
    for i in range(10):
        _make_event(source=f"task.{i}", message=f"event {i}")

    resp = client.get("/api/errors/?limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 3
    assert body["count"] == 3

    resp2 = client.get("/api/errors/?limit=9999")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["results"]) <= 200


@pytest.mark.django_db
def test_get_errors_default_limit_is_50():
    """With no limit param, returns at most 50 events."""
    client = Client()
    for i in range(55):
        _make_event(source=f"task.{i}")

    resp = client.get("/api/errors/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 50


@pytest.mark.django_db
def test_resolve_flips_resolved_to_true():
    """POST .../resolve/ sets resolved=True and returns the updated row."""
    client = Client()
    ev = _make_event(resolved=False)
    assert ev.resolved is False

    resp = client.post(f"/api/errors/{ev.pk}/resolve/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ev.pk
    assert body["resolved"] is True

    ev.refresh_from_db()
    assert ev.resolved is True


@pytest.mark.django_db
def test_resolve_nonexistent_returns_404():
    """Resolving a non-existent event returns 404."""
    client = Client()
    resp = client.post("/api/errors/99999/resolve/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_resolve_already_resolved_is_idempotent():
    """Resolving an already-resolved event returns 200 and stays resolved."""
    client = Client()
    ev = _make_event(resolved=True)

    resp = client.post(f"/api/errors/{ev.pk}/resolve/")
    assert resp.status_code == 200
    assert resp.json()["resolved"] is True
