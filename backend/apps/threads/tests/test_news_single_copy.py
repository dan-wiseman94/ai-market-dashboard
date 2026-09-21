"""News reaches Claude once, as citable blocks — not twice.

`serialize_for_ai` renders a "## News" prose section into the pinned-snapshot
turn's text, and `_message_content` also attaches the same items as
`search_result` blocks. Sending both doubles the news input tokens and buries the
copy the model can actually cite.
"""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads._request import _message_content, _strip_news_prose
from apps.threads.models import Message, Thread

_SERIALIZED = """**Objective:** Read the tape

> **Captured:** 2026-09-20 14:00 UTC (2m ago).

## Quotes
- SPY 500.00

## News (last 24h)

- **14:00** — *Reuters* — Fed holds rates
  The committee left the target range unchanged.
- **13:40** — *AP* — Chips rally

## Market breadth
- advancers 1800"""


def test_strip_news_prose_removes_only_the_news_section():
    out = _strip_news_prose(_SERIALIZED)

    assert "Fed holds rates" not in out
    assert "## News" not in out
    assert "## Quotes" in out
    assert "## Market breadth" in out
    assert "advancers 1800" in out
    assert "**Objective:** Read the tape" in out


def test_strip_news_prose_is_a_noop_without_a_news_section():
    text = "## Quotes\n- SPY 500.00"

    assert _strip_news_prose(text) == text


def test_strip_news_prose_handles_news_as_the_last_section():
    text = "## Quotes\n- SPY 500.00\n\n## News (last 24h)\n\n- **14:00** — *AP* — x"

    assert _strip_news_prose(text) == "## Quotes\n- SPY 500.00"


@pytest.fixture
def snapshot_turn(db):
    prof = TradingProfile.objects.create(name="p", style="s")
    snap = Snapshot.objects.create(profile=prof, objective="Read the tape", status="ready")
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="news",
        status="done",
        payload={
            "items": [
                {
                    "id": 1,
                    "headline": "Fed holds rates",
                    "source": "Reuters",
                    "summary": "The committee left the target range unchanged.",
                    "url": "https://example.test/fed",
                }
            ]
        },
    )
    thread = Thread.objects.create(kind="consult", profile=prof)
    msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": _SERIALIZED},
        status="done",
        snapshot_ref=snap,
    )
    return msg


def test_claude_gets_search_result_blocks_and_no_prose_copy(snapshot_turn):
    content = _message_content(snapshot_turn, provider_name="claude")

    assert isinstance(content, list)
    results = [b for b in content if b.get("type") == "search_result"]
    assert len(results) == 1
    text_blocks = [b["text"] for b in content if b.get("type") == "text"]
    assert len(text_blocks) == 1
    # One copy only: the headline lives in the citable block, not the prose.
    assert "Fed holds rates" not in text_blocks[0]
    assert "## Quotes" in text_blocks[0]


def test_other_providers_keep_the_prose_copy(snapshot_turn):
    # No `search_result` shape outside Anthropic, so the prose is the only copy.
    content = _message_content(snapshot_turn, provider_name="openai")

    assert isinstance(content, str)
    assert "Fed holds rates" in content
