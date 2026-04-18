# backend/apps/export/tests/test_serialize_thread.py
from __future__ import annotations

import json

import pytest

from apps.export.serializers import thread_to_json, thread_to_markdown
from apps.threads.models import Message, Thread


@pytest.fixture
def seeded_thread(db):
    t = Thread.objects.create(kind="chat", title="Alpha")
    Message.objects.create(thread=t, role="user", content={"text": "hi"}, status="done")
    Message.objects.create(thread=t, role="assistant", content={"text": "hello back"}, status="done")
    return t


def test_thread_to_json_includes_messages(seeded_thread) -> None:
    out = thread_to_json(seeded_thread)
    assert out["id"] == seeded_thread.id
    assert out["title"] == "Alpha"
    assert len(out["messages"]) == 2
    assert out["messages"][0]["role"] == "user"
    # No secrets
    assert "api_key" not in json.dumps(out).lower()


def test_thread_to_markdown_chronological(seeded_thread) -> None:
    md = thread_to_markdown(seeded_thread)
    assert "# Alpha" in md
    assert "## User" in md
    assert "hi" in md
    assert "hello back" in md
    assert md.index("hi") < md.index("hello back")


def test_thread_json_contains_no_secret_fields(seeded_thread) -> None:
    """Guard — regardless of future model fields, serializer never leaks."""
    s = json.dumps(thread_to_json(seeded_thread)).lower()
    for forbidden in ("api_key", "access_token", "refresh_token", "secret"):
        assert forbidden not in s
