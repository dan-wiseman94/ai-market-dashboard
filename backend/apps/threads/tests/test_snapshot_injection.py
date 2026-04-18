"""Thread creation with a pinned snapshot must synthesize a user message whose
text is the serialized snapshot payload, so the LLM actually sees the market data.

Regression guard for the pre-fix state where `pinned_snapshot` was stored as an FK
but its content never reached the provider call.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.models import Message, Thread


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="Day trader", style="Aggressive intraday")


@pytest.fixture
def ready_snapshot(db, profile) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile,
        objective="Gauge SPY intraday momentum",
        notes="pre-FOMC",
        status="ready",
        includes=["quotes", "breadth"],
        source="manual",
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done",
        payload={"SPY": {"last": 521.30, "pct_change": 0.42, "bid": 521.28,
                         "ask": 521.31, "volume": 1_234_567, "high": 522.0,
                         "low": 520.1}},
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="breadth", status="done",
        payload={"spy_last": 521.30, "qqq_last": 445.10, "vix_last": 14.2,
                 "sectors": {"XLK": 215.4}, "breadth": {}},
    )
    return snap


@pytest.mark.django_db
def test_thread_create_with_pinned_snapshot_injects_first_user_message(
    profile, ready_snapshot,
) -> None:
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={
            "kind": "consult",
            "profile_id": profile.id,
            "pinned_snapshot_id": ready_snapshot.id,
            "title": "SPY read",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content

    thread = Thread.objects.get(id=resp.json()["id"])
    first = Message.objects.filter(thread=thread, role="user").order_by("created_at").first()
    assert first is not None, "expected a synthetic user message"
    assert first.status == "done"
    assert first.snapshot_ref_id == ready_snapshot.id

    text = first.content["text"]
    assert "Gauge SPY intraday momentum" in text, "objective missing from payload"
    assert "SPY" in text and "521.30" in text, "quotes section missing"
    assert "VIX" in text and "14.2" in text, "breadth section missing"


@pytest.mark.django_db
def test_thread_create_without_pinned_snapshot_has_no_synthetic_message(
    profile,
) -> None:
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "title": "open chat"},
        format="json",
    )
    assert resp.status_code == 201
    thread = Thread.objects.get(id=resp.json()["id"])
    assert Message.objects.filter(thread=thread).count() == 0


@pytest.mark.django_db
def test_thread_create_with_unknown_snapshot_id_no_crash(profile) -> None:
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": 999_999},
        format="json",
    )
    assert resp.status_code == 201
    thread = Thread.objects.get(id=resp.json()["id"])
    assert thread.pinned_snapshot is None
    assert Message.objects.filter(thread=thread).count() == 0


@pytest.mark.django_db
def test_thread_create_refuses_non_ready_snapshot(profile) -> None:
    """Pinning a pending/failed snapshot would inject all-stub noise. Reject with 400."""
    pending = Snapshot.objects.create(
        profile=profile, status="pending", includes=["quotes"], source="manual",
    )
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": pending.id},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "snapshot_not_ready"
    assert Thread.objects.count() == 0  # atomic: no thread created on refusal


@pytest.mark.django_db
def test_build_request_includes_snapshot_on_first_user_turn(
    profile, ready_snapshot,
) -> None:
    """After thread creation + one user follow-up, _build_request should emit
    [system=profile.style, user=snapshot_markdown, user=follow_up]."""
    from apps.threads.tasks import _build_request

    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={
            "kind": "consult",
            "profile_id": profile.id,
            "pinned_snapshot_id": ready_snapshot.id,
        },
        format="json",
    )
    thread_id = resp.json()["id"]
    thread = Thread.objects.select_related("profile").get(id=thread_id)

    follow_up = Message.objects.create(
        thread=thread, role="user",
        content={"text": "What do you see?"}, status="done",
    )

    req = _build_request(thread, follow_up)
    assert req.system == "Aggressive intraday"
    assert len(req.messages) == 2
    assert req.messages[0].role == "user"
    assert "Gauge SPY intraday momentum" in req.messages[0].content
    assert "SPY" in req.messages[0].content
    assert req.messages[1].role == "user"
    assert req.messages[1].content == "What do you see?"
