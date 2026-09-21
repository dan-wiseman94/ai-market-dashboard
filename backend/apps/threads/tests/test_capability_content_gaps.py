"""Claude-only CONTENT is reported, not silently dropped.

`_message_content` strips Files-API document blocks and news `search_result`
blocks for every non-Claude provider. Without these gaps the user sends a PDF to
an OpenAI profile and is told nothing at all.
"""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads._request import claude_only_content_kinds
from apps.threads.models import Message, Thread


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="p", style="s")


def _thread(profile):
    return Thread.objects.create(kind="chat", profile=profile)


def test_document_block_is_reported(profile):
    thread = _thread(profile)
    msg = Message.objects.create(
        thread=thread,
        role="user",
        status="done",
        content={
            "blocks": [
                {"type": "document", "source": {"type": "file", "file_id": "file_x"}},
                {"type": "text", "text": "summarize this"},
            ]
        },
    )

    assert claude_only_content_kinds(thread, msg) == ["file attachments"]


def test_plain_text_turn_reports_nothing(profile):
    thread = _thread(profile)
    msg = Message.objects.create(thread=thread, role="user", status="done", content={"text": "hi"})

    assert claude_only_content_kinds(thread, msg) == []


def test_snapshot_news_is_reported_on_a_later_turn(profile):
    snap = Snapshot.objects.create(profile=profile, objective="o", status="ready")
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="news",
        status="done",
        payload={"items": [{"id": 1, "headline": "h"}]},
    )
    thread = _thread(profile)
    Message.objects.create(
        thread=thread, role="user", status="done", content={"text": "snap"}, snapshot_ref=snap
    )
    follow_up = Message.objects.create(
        thread=thread, role="user", status="done", content={"text": "and now?"}
    )

    assert claude_only_content_kinds(thread, follow_up) == ["news citations"]


def test_snapshot_without_news_reports_nothing(profile):
    snap = Snapshot.objects.create(profile=profile, objective="o", status="ready")
    thread = _thread(profile)
    msg = Message.objects.create(
        thread=thread, role="user", status="done", content={"text": "snap"}, snapshot_ref=snap
    )

    assert claude_only_content_kinds(thread, msg) == []


def test_unsupported_features_carries_content_kinds_through():
    from apps.ai.capabilities import unsupported_features

    out = unsupported_features(
        "openai", None, supports_tools=True, content_kinds=["file attachments"]
    )

    assert out == ["file attachments"]


def test_claude_reports_no_gaps_even_with_content_kinds():
    from apps.ai.capabilities import unsupported_features

    assert unsupported_features("claude", None, supports_tools=False, content_kinds=["x"]) == []
