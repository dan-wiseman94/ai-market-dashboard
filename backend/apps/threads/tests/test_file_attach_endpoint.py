"""POST /api/threads/<id>/attach-file/ creates a user Message with blocks content."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread, UserFile


@pytest.fixture
def thread(db):
    p = TradingProfile.objects.create(
        name="p",
        style="s",
        default_provider="claude",
        default_model="claude-opus-4-8",
    )
    return Thread.objects.create(kind="consult", profile=p)


@pytest.fixture
def file_row(db) -> UserFile:
    return UserFile.objects.create(
        anthropic_id="file_abc",
        kind="filing",
        ticker="AAPL",
        mime="application/pdf",
        size=123,
        filename="10k.pdf",
    )


def test_attach_file_creates_blocks_message(db, thread, file_row) -> None:
    client = APIClient()
    resp = client.post(
        f"/api/threads/{thread.id}/attach-file/",
        data={"file_id": file_row.id, "prompt": "Summarize key risks."},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    msg = Message.objects.filter(thread=thread, role="user").latest("id")
    blocks = msg.content["blocks"]
    assert any(b["type"] == "document" for b in blocks)
    doc = next(b for b in blocks if b["type"] == "document")
    assert doc["source"]["file_id"] == "file_abc"
    assert any(b["type"] == "text" and "risks" in b["text"] for b in blocks)


def test_attach_unknown_file_404(db, thread) -> None:
    client = APIClient()
    resp = client.post(
        f"/api/threads/{thread.id}/attach-file/",
        data={"file_id": 99999, "prompt": "x"},
        format="json",
    )
    assert resp.status_code == 404


def test_attach_file_default_prompt(db, thread, file_row) -> None:
    client = APIClient()
    resp = client.post(
        f"/api/threads/{thread.id}/attach-file/",
        data={"file_id": file_row.id},
        format="json",
    )
    assert resp.status_code == 201
    msg = Message.objects.filter(thread=thread, role="user").latest("id")
    text_block = next(b for b in msg.content["blocks"] if b["type"] == "text")
    assert "review" in text_block["text"].lower()


# ---------------------------------------------------------------------------
# The attached document must actually REACH the model — a "blocks" content
# threads through as a provider content-block list, not a stringified dict.
# ---------------------------------------------------------------------------


def _attach(thread, file_row, prompt="Summarize key risks.") -> Message:
    Message.objects.create(
        thread=thread,
        role="user",
        status="done",
        content={
            "blocks": [
                {"type": "document", "source": {"type": "file", "file_id": file_row.anthropic_id}},
                {"type": "text", "text": prompt},
            ]
        },
    )
    return Message.objects.filter(thread=thread, role="user").latest("id")


def test_attached_document_threads_through_for_claude(db, thread, file_row) -> None:
    from apps.threads._request import _message_content

    msg = _attach(thread, file_row)
    content = _message_content(msg, provider_name="claude")
    assert isinstance(content, list), f"expected block list, got {content!r}"
    doc = next((b for b in content if b.get("type") == "document"), None)
    assert doc is not None and doc["source"]["file_id"] == "file_abc"
    # the prompt text rides along; nothing is a stringified dict
    assert any(b.get("type") == "text" and "risks" in b.get("text", "") for b in content)
    assert "'blocks'" not in str(content)


def test_attached_document_text_only_for_non_claude(db, thread, file_row) -> None:
    from apps.threads._request import _message_content

    msg = _attach(thread, file_row)
    # OpenAI/Local cannot render an Anthropic document block — they get the text,
    # never the Python repr of the content dict.
    content = _message_content(msg, provider_name="openai")
    assert content == "Summarize key risks."


def test_extract_text_reads_block_text_not_repr(db, thread, file_row) -> None:
    from apps.threads._request import _extract_text

    msg = _attach(thread, file_row, prompt="What are the risks?")
    assert _extract_text(msg) == "What are the risks?"
