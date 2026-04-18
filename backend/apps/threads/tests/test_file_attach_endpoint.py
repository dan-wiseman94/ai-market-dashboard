"""POST /api/threads/<id>/attach-file/ creates a user Message with blocks content."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.files.models import UserFile
from apps.profiles.models import TradingProfile
from apps.threads.models import Message, Thread


@pytest.fixture
def thread(db):
    p = TradingProfile.objects.create(
        name="p", style="s",
        default_provider="claude", default_model="claude-opus-4-7",
    )
    return Thread.objects.create(kind="consult", profile=p)


@pytest.fixture
def file_row(db) -> UserFile:
    return UserFile.objects.create(
        anthropic_id="file_abc", kind="filing", ticker="AAPL",
        mime="application/pdf", size=123, filename="10k.pdf",
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
    doc = [b for b in blocks if b["type"] == "document"][0]
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
