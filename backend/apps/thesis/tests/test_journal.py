"""Tests for the decision journal API — create + list + filter."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.thesis.models import DecisionJournalEntry, Thesis
from apps.threads.models import Thread

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="Test Profile", style="swing trader")


@pytest.fixture
def thread(db, profile):
    return Thread.objects.create(kind="consult", title="Thread A", profile=profile)


@pytest.fixture
def thread2(db, profile):
    return Thread.objects.create(kind="consult", title="Thread B", profile=profile)


@pytest.fixture
def snapshot(db, profile):
    return Snapshot.objects.create(
        profile=profile, includes=["quotes"], source="manual", status="ready"
    )


@pytest.fixture
def thesis(db, profile):
    return Thesis.objects.create(
        title="AAPL long", ticker="AAPL", direction="bullish", profile=profile
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_minimal(api, thread):
    """POST with only thread_id + decision creates an entry (201)."""
    resp = api.post(
        "/api/journal/",
        {"thread_id": thread.id, "decision": "acted"},
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["thread_id"] == thread.id
    assert body["decision"] == "acted"
    assert body["note"] == ""
    assert body["thesis_id"] is None
    assert body["snapshot_id"] is None
    assert "id" in body
    assert "created_at" in body


@pytest.mark.django_db
def test_create_with_note(api, thread):
    resp = api.post(
        "/api/journal/",
        {"thread_id": thread.id, "decision": "passed", "note": "Spread too wide"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["note"] == "Spread too wide"


@pytest.mark.django_db
def test_create_with_thesis_and_snapshot(api, thread, thesis, snapshot):
    """Links thesis_id and snapshot_id correctly."""
    resp = api.post(
        "/api/journal/",
        {
            "thread_id": thread.id,
            "decision": "hedged",
            "thesis_id": thesis.id,
            "snapshot_id": snapshot.id,
            "note": "Added collar",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["thesis_id"] == thesis.id
    assert body["snapshot_id"] == snapshot.id
    # Verify DB
    entry = DecisionJournalEntry.objects.get(id=body["id"])
    assert entry.thesis_id == thesis.id
    assert entry.snapshot_id == snapshot.id


@pytest.mark.django_db
def test_create_watching_decision(api, thread):
    resp = api.post(
        "/api/journal/",
        {"thread_id": thread.id, "decision": "watching"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["decision"] == "watching"


# ---------------------------------------------------------------------------
# Create validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_missing_thread_id_returns_400(api):
    resp = api.post(
        "/api/journal/",
        {"decision": "acted"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_missing_decision_returns_400(api, thread):
    resp = api.post(
        "/api/journal/",
        {"thread_id": thread.id},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_invalid_decision_returns_400(api, thread):
    resp = api.post(
        "/api/journal/",
        {"thread_id": thread.id, "decision": "bought"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_invalid_thread_id_returns_400(api):
    """Non-existent thread_id should be rejected."""
    resp = api.post(
        "/api/journal/",
        {"thread_id": 999999, "decision": "acted"},
        format="json",
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List + filter
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_all_returns_all_entries(api, thread, thread2):
    """GET /api/journal/ returns entries from all threads."""
    DecisionJournalEntry.objects.create(thread=thread, decision="acted")
    DecisionJournalEntry.objects.create(thread=thread2, decision="passed")
    resp = api.get("/api/journal/", format="json")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.django_db
def test_list_filter_by_thread(api, thread, thread2):
    """GET /api/journal/?thread=<id> returns only that thread's entries."""
    DecisionJournalEntry.objects.create(thread=thread, decision="acted")
    DecisionJournalEntry.objects.create(thread=thread, decision="watching")
    DecisionJournalEntry.objects.create(thread=thread2, decision="passed")
    resp = api.get(f"/api/journal/?thread={thread.id}", format="json")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert all(row["thread_id"] == thread.id for row in data)


@pytest.mark.django_db
def test_list_ordered_newest_first(api, thread):
    """Entries returned newest-first."""
    e1 = DecisionJournalEntry.objects.create(thread=thread, decision="acted")
    e2 = DecisionJournalEntry.objects.create(thread=thread, decision="passed")
    resp = api.get(f"/api/journal/?thread={thread.id}", format="json")
    data = resp.json()
    ids = [row["id"] for row in data]
    # e2 was created after e1, so it should appear first
    assert ids.index(e2.id) < ids.index(e1.id)


@pytest.mark.django_db
def test_list_filter_nonexistent_thread_returns_empty(api):
    """Filter by a thread that doesn't exist returns empty list, not an error."""
    resp = api.get("/api/journal/?thread=999999", format="json")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_list_filter_non_integer_thread_returns_200_empty(api):
    """GET /api/journal/?thread=foo returns 200 with empty list (not 500)."""
    resp = api.get("/api/journal/?thread=foo", format="json")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Response shape (*_id convention)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_response_uses_star_id_keys(api, thread, thesis, snapshot):
    """Verify the response serializer uses thread_id / thesis_id / snapshot_id."""
    resp = api.post(
        "/api/journal/",
        {
            "thread_id": thread.id,
            "decision": "acted",
            "thesis_id": thesis.id,
            "snapshot_id": snapshot.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    # Must use *_id keys, not nested objects
    assert "thread_id" in body
    assert "thesis_id" in body
    assert "snapshot_id" in body
    assert "thread" not in body
    assert "thesis" not in body
    assert "snapshot" not in body
