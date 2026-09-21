"""The chat path carries a tool-round ceiling.

Cost caps are checked once, before the stream opens; every tool round after that
re-sends the whole ~30k-token prompt and is billed with nothing to stop it. The
ceiling comes from SystemSettings so it is tunable without a restart.
"""

from __future__ import annotations

import pytest

from apps.core.models import SystemSettings
from apps.profiles.models import TradingProfile
from apps.threads._request import _build_request
from apps.threads.models import Message, Thread


@pytest.fixture
def chat_turn(db):
    prof = TradingProfile.objects.create(name="p", style="s", enable_tools=False)
    thread = Thread.objects.create(kind="chat", profile=prof)
    user = Message.objects.create(thread=thread, role="user", content={"text": "hi"}, status="done")
    return thread, user


def test_chat_request_is_bounded_by_default(chat_turn):
    thread, user = chat_turn
    req = _build_request(thread, user, provider_name="claude")

    assert req.max_tool_iterations > 0


def test_ceiling_follows_system_settings(chat_turn):
    thread, user = chat_turn
    cfg = SystemSettings.load()
    cfg.ai_chat_max_tool_iterations = 3
    cfg.save()

    req = _build_request(thread, user, provider_name="claude")

    assert req.max_tool_iterations == 3


def test_max_tokens_leaves_room_for_a_reasoning_answer(chat_turn):
    thread, user = chat_turn
    req = _build_request(thread, user, provider_name="claude")

    # Also the invariant the budget-shaped rows need: budget_tokens < max_tokens.
    assert req.max_tokens > 8_000
