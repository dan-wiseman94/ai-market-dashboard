"""Thread creation with a pinned snapshot must synthesize a user message whose
text is the serialized snapshot payload, so the LLM actually sees the market data.

Regression guard for the pre-fix state where `pinned_snapshot` was stored as an FK
but its content never reached the provider call.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage, SnapshotSection
from apps.threads.models import Message, Thread
from apps.threads.tasks import _build_request


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
        snapshot=snap,
        kind="quotes",
        status="done",
        payload={
            "SPY": {
                "last": 521.30,
                "pct_change": 0.42,
                "bid": 521.28,
                "ask": 521.31,
                "volume": 1_234_567,
                "high": 522.0,
                "low": 520.1,
            }
        },
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="breadth",
        status="done",
        payload={
            "spy_last": 521.30,
            "qqq_last": 445.10,
            "vix_last": 14.2,
            "sectors": {"XLK": 215.4},
            "breadth": {},
        },
    )
    return snap


@pytest.mark.django_db
def test_thread_create_with_pinned_snapshot_injects_first_user_message(
    profile,
    ready_snapshot,
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
def test_thread_create_budgets_payload_for_profile_model(profile) -> None:
    """The synthetic snapshot message must be budgeted for the profile's model,
    not the 40k fallback. A snapshot that fits Claude's 150k budget but exceeds
    40k must reach the model whole — regression guard for serialize_for_ai being
    called without provider/model (which silently pruned large snapshots).
    """
    from apps.snapshots.serializer import serialize_for_ai

    # ~2500 tickers renders to >40k tokens but well under Claude's 150k budget.
    big_quotes = {
        f"TKR{i:04d}": {
            "last": 521.30,
            "pct_change": 0.42,
            "bid": 521.28,
            "ask": 521.31,
            "volume": 1_234_567,
            "high": 522.0,
            "low": 520.1,
        }
        for i in range(2500)
    }
    snap = Snapshot.objects.create(
        profile=profile,
        objective="Wide scan",
        status="ready",
        includes=["quotes"],
        source="manual",
    )
    SnapshotSection.objects.create(snapshot=snap, kind="quotes", status="done", payload=big_quotes)

    # Teeth: the old default-arg call (40k budget) prunes the quotes section.
    assert "_(pruned for token budget" in serialize_for_ai(snap)

    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": snap.id},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    thread = Thread.objects.get(id=resp.json()["id"])
    first = Message.objects.filter(thread=thread, role="user").get()
    text = first.content["text"]
    # profile defaults to Claude (150k) → nothing pruned, every ticker present.
    assert "_(pruned for token budget" not in text
    assert "TKR0000" in text and "TKR2499" in text


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
        profile=profile,
        status="pending",
        includes=["quotes"],
        source="manual",
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
    profile,
    ready_snapshot,
) -> None:
    """After thread creation + one user follow-up, _build_request should emit
    [system=profile.style, user=snapshot_markdown, user=follow_up]."""
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
        thread=thread,
        role="user",
        content={"text": "What do you see?"},
        status="done",
    )

    req = _build_request(thread, follow_up)
    assert req.system == "Aggressive intraday"
    assert len(req.messages) == 2
    assert req.messages[0].role == "user"
    assert "Gauge SPY intraday momentum" in req.messages[0].content
    assert "SPY" in req.messages[0].content
    assert req.messages[1].role == "user"
    assert req.messages[1].content == "What do you see?"


@pytest.mark.django_db
def test_build_request_attaches_snapshot_images_as_blocks(profile, ready_snapshot) -> None:
    """A pinned snapshot with a captured chart image must reach the model as an
    image block, not just a text caption.

    Regression guard: image sections are saved status="done" (SnapshotSection has
    no "ready" status), but `_snapshot_image_ids` previously filtered status="ready"
    so images were silently never attached.
    """
    img = SnapshotImage.objects.create(
        snapshot=ready_snapshot,
        kind="server_render",
        data=b"\x89PNG\r\n\x1a\n fake png bytes",
        mime_type="image/png",
    )
    SnapshotSection.objects.create(
        snapshot=ready_snapshot,
        kind="image",
        status="done",
        payload={"image_ids": [img.id]},
    )

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
    assert resp.status_code == 201, resp.content
    thread = Thread.objects.select_related("profile").get(id=resp.json()["id"])
    snap_msg = Message.objects.filter(thread=thread, role="user").order_by("created_at").first()
    assert snap_msg is not None and snap_msg.snapshot_ref_id == ready_snapshot.id

    req = _build_request(thread, snap_msg, provider_name="claude")
    first = req.messages[0]
    assert isinstance(first.content, list), (
        "snapshot message content must be a block list when images are present, "
        f"got {type(first.content).__name__}"
    )
    image_blocks = [b for b in first.content if b.get("type") == "image"]
    assert len(image_blocks) == 1, "captured chart image must be attached as an image block"
    assert image_blocks[0]["source"]["media_type"] == "image/png"


@pytest.mark.django_db
def test_build_request_attaches_news_as_search_result_blocks(profile, ready_snapshot) -> None:
    """A pinned snapshot's news section must reach Claude as citable search_result
    blocks, not only as markdown text.

    Regression guard: news_to_search_result_blocks existed but was never wired into
    the request, so the model could never produce news citations.
    """
    SnapshotSection.objects.create(
        snapshot=ready_snapshot,
        kind="news",
        status="done",
        payload={
            "items": [
                {
                    "id": 1,
                    "headline": "SPY rips higher into the close",
                    "summary": "Broad-based rally.",
                    "source": "Reuters",
                    "url": "https://ex.com/a",
                }
            ]
        },
    )
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": ready_snapshot.id},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    thread = Thread.objects.select_related("profile").get(id=resp.json()["id"])
    snap_msg = Message.objects.filter(thread=thread, role="user").order_by("created_at").first()

    req = _build_request(thread, snap_msg, provider_name="claude")
    first = req.messages[0]
    assert isinstance(first.content, list)
    blocks = [b for b in first.content if b.get("type") == "search_result"]
    assert len(blocks) == 1, "news items must be attached as search_result blocks"
    assert blocks[0]["source"] == "https://ex.com/a"
    assert blocks[0]["citations"] == {"enabled": True}


@pytest.mark.django_db
def test_news_search_result_blocks_are_claude_only(profile, ready_snapshot) -> None:
    """search_result blocks are an Anthropic shape; non-Claude providers keep news
    as plain markdown text (no blocks)."""
    SnapshotSection.objects.create(
        snapshot=ready_snapshot,
        kind="news",
        status="done",
        payload={"items": [{"id": 1, "headline": "h", "summary": "s", "source": "x", "url": "u"}]},
    )
    client = APIClient()
    resp = client.post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": ready_snapshot.id},
        format="json",
    )
    thread = Thread.objects.select_related("profile").get(id=resp.json()["id"])
    snap_msg = Message.objects.filter(thread=thread, role="user").order_by("created_at").first()

    req = _build_request(thread, snap_msg, provider_name="openai")
    # No images on this snapshot and news is Claude-only → plain text content.
    assert isinstance(req.messages[0].content, str)
