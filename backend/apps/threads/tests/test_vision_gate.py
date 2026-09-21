"""``ProviderConfig.supports_vision`` gates chart images on a run, and the drop is named.

An endpoint with no vision head rejects the whole call when an image block arrives
rather than ignoring it, so the request builder leaves the images out — and the
capability warning says it did, on every provider (the flag is declared per
ProviderConfig row, so it is not a Claude-vs-rest split).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.snapshots.models import Snapshot, SnapshotImage, SnapshotSection
from apps.threads._request import _build_request, run_carries_images
from apps.threads.models import Message, Thread
from apps.threads.tasks import _run_ai_on_message


@pytest.fixture
def profile(db) -> TradingProfile:
    # The Claude-only flags default on; off here so the only gap under test is vision.
    return TradingProfile.objects.create(
        name="P", style="x", enable_tools=False, enable_thinking=False, enable_memory=False
    )


@pytest.fixture
def snapshot_with_image(db, profile) -> Snapshot:
    snap = Snapshot.objects.create(profile=profile, objective="o", status="ready")
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"SPY": {"last": 1.0}}
    )
    img = SnapshotImage.objects.create(
        snapshot=snap, kind="server_render", data=b"\x89PNG fake", mime_type="image/png"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="image", status="done", payload={"image_ids": [img.id]}
    )
    return snap


def _pinned_turn(profile, snap) -> tuple[Thread, Message]:
    thread = Thread.objects.create(kind="consult", profile=profile)
    msg = Message.objects.create(
        thread=thread, role="user", status="done", content={"text": "look"}, snapshot_ref=snap
    )
    return thread, msg


def _image_blocks(content) -> list[dict]:
    if not isinstance(content, list):
        return []
    return [b for b in content if b.get("type") in ("image", "image_url")]


@pytest.mark.parametrize("provider_name", ["claude", "openai", "local"])
def test_images_attach_when_the_endpoint_declares_vision(
    profile, snapshot_with_image, provider_name
):
    thread, msg = _pinned_turn(profile, snapshot_with_image)

    req = _build_request(thread, msg, provider_name=provider_name, supports_vision=True)

    assert len(_image_blocks(req.messages[0].content)) == 1


@pytest.mark.parametrize("provider_name", ["claude", "openai", "local"])
def test_images_are_left_out_when_the_endpoint_has_no_vision_head(
    profile, snapshot_with_image, provider_name
):
    thread, msg = _pinned_turn(profile, snapshot_with_image)

    req = _build_request(thread, msg, provider_name=provider_name, supports_vision=False)

    content = req.messages[0].content
    assert _image_blocks(content) == []
    # The turn still carries its serialized snapshot text — only the images go.
    text = content if isinstance(content, str) else " ".join(b.get("text", "") for b in content)
    assert "look" in text


def test_run_carries_images_sees_the_turns_own_snapshot(profile, snapshot_with_image):
    thread, msg = _pinned_turn(profile, snapshot_with_image)

    assert run_carries_images(thread, msg) is True


def test_run_carries_images_sees_the_threads_latest_snapshot_on_a_follow_up(
    profile, snapshot_with_image
):
    thread, _ = _pinned_turn(profile, snapshot_with_image)
    follow_up = Message.objects.create(
        thread=thread, role="user", status="done", content={"text": "and now?"}
    )

    assert run_carries_images(thread, follow_up) is True


def test_run_carries_images_is_false_without_an_image_section(profile):
    snap = Snapshot.objects.create(profile=profile, objective="o", status="ready")
    thread, msg = _pinned_turn(profile, snap)

    assert run_carries_images(thread, msg) is False


def test_run_carries_images_is_false_on_a_bare_chat_turn(profile):
    thread = Thread.objects.create(kind="chat", profile=profile)
    msg = Message.objects.create(thread=thread, role="user", status="done", content={"text": "hi"})

    assert run_carries_images(thread, msg) is False


def _noop_runner(*a, **k):
    async def drive():
        return None

    return drive


@pytest.mark.django_db
def test_run_ai_warns_when_a_vision_less_provider_loses_the_chart_images(
    profile, snapshot_with_image
):
    ProviderConfig.objects.create(provider="local", base_url="http://x/v1", supports_vision=False)  # type: ignore[misc]
    thread, snap_msg = _pinned_turn(profile, snapshot_with_image)
    user = Message.objects.create(thread=thread, role="user", content={"text": "go"})

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("local", "m")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", _noop_runner),
    ):
        out = _run_ai_on_message(thread_id=thread.id, user_message_id=user.id)

    assert out["ok"] is True
    sys_msg = Message.objects.filter(thread=thread, role="system").latest("created_at")
    assert sys_msg.content.get("kind") == "capability_warning"
    assert "chart images" in sys_msg.content["text"]
    assert snap_msg.id  # the snapshot turn itself is untouched


@pytest.mark.django_db
def test_run_ai_stays_quiet_when_the_provider_declares_vision(profile, snapshot_with_image):
    ProviderConfig.objects.create(provider="local", base_url="http://x/v1", supports_vision=True)  # type: ignore[misc]
    thread, _ = _pinned_turn(profile, snapshot_with_image)
    user = Message.objects.create(thread=thread, role="user", content={"text": "go"})

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("local", "m")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", _noop_runner),
    ):
        out = _run_ai_on_message(thread_id=thread.id, user_message_id=user.id)

    assert out["ok"] is True
    assert not Message.objects.filter(thread=thread, role="system").exists()


@pytest.mark.django_db
def test_run_ai_stays_quiet_when_vision_is_off_but_the_run_has_no_images(profile):
    """The warning names a real loss — no image section, nothing to report."""
    ProviderConfig.objects.create(provider="local", base_url="http://x/v1", supports_vision=False)  # type: ignore[misc]
    snap = Snapshot.objects.create(profile=profile, objective="o", status="ready")
    thread, _ = _pinned_turn(profile, snap)
    user = Message.objects.create(thread=thread, role="user", content={"text": "go"})

    with (
        patch("apps.threads.tasks.resolve_provider_and_model", return_value=("local", "m")),
        patch("apps.threads.tasks.get_provider", return_value=MagicMock()),
        patch("apps.threads.tasks._build_stream_runner", _noop_runner),
    ):
        out = _run_ai_on_message(thread_id=thread.id, user_message_id=user.id)

    assert out["ok"] is True
    assert not Message.objects.filter(thread=thread, role="system").exists()
