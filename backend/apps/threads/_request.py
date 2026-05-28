"""Build a provider RunRequest from a Thread's message history.

Split out of ``tasks.py``: pure request assembly with no broadcast/streaming
side effects. ``tasks.py`` re-exports ``_extract_text`` and ``_build_request``
so existing ``apps.threads.tasks.*`` import/patch sites keep working.
"""

from __future__ import annotations

from typing import cast

from apps.ai.citations import news_to_search_result_blocks
from apps.ai.types import ChatMessage, RoleType, RunRequest
from apps.snapshots.models import SnapshotSection
from apps.snapshots.serializer import build_image_blocks
from apps.threads.models import Message, Thread


def _extract_text(m: Message) -> str:
    c = m.content or {}
    if isinstance(c, dict) and "text" in c:
        return c["text"]
    return str(c)


def _snapshot_image_ids(snapshot_id: int) -> list[int]:
    # Section terminal state is "done" (only the parent Snapshot uses "ready").
    section = SnapshotSection.objects.filter(
        snapshot_id=snapshot_id, kind="image", status="done"
    ).first()
    if section is None:
        return []
    payload = section.payload or {}
    return list(payload.get("image_ids") or [])


def _snapshot_news_items(snapshot_id: int) -> list[dict]:
    section = SnapshotSection.objects.filter(
        snapshot_id=snapshot_id, kind="news", status="done"
    ).first()
    if section is None:
        return []
    payload = section.payload or {}
    return list(payload.get("items") or [])


def _message_content(
    m: Message,
    *,
    provider_name: str,
) -> str | list[dict]:
    """Return the ChatMessage content for a Message — string, or blocks if the
    message references a Snapshot with image sections. Images are attached to
    the message regardless of provider; the serializer handles provider shape.
    """
    text = _extract_text(m)
    snap_id = getattr(m, "snapshot_ref_id", None)
    if not snap_id:
        return text
    blocks: list[dict] = []
    # News as citable search_result blocks — Anthropic-only shape, so Claude only.
    if provider_name == "claude":
        news_items = _snapshot_news_items(snap_id)
        if news_items:
            blocks.extend(news_to_search_result_blocks(news_items))
    # Chart images attach for every provider; build_image_blocks picks the shape.
    image_ids = _snapshot_image_ids(snap_id)
    if image_ids:
        blocks.extend(build_image_blocks(image_ids, provider_name=provider_name))
    if not blocks:
        return text
    blocks.append({"type": "text", "text": text})
    return blocks


def _history_messages(thread: Thread) -> list[Message]:
    """Prior done user/assistant turns, oldest first.

    Picks up the synthetic pinned-snapshot Message (a done user turn) created by
    ThreadViewSet.create — do not load the snapshot here.
    """
    return list(
        Message.objects.filter(
            thread=thread, role__in=["user", "assistant"], status="done"
        ).order_by("created_at")
    )


def _resolve_capabilities(
    thread: Thread,
    *,
    provider_name: str,
    supports_tools: bool,
) -> tuple[list[dict], int, str]:
    """Resolve opt-in tools / thinking budget / memory dir for the run.

    Tools: Claude always (anthropic shape); OpenAI/local when the endpoint opts
    in (openai shape). Thinking + memory remain Claude-only.
    """
    if thread.profile is None:
        return [], 0, ""

    profile = thread.profile
    tools: list[dict] = []
    if getattr(profile, "enable_tools", False) and (provider_name == "claude" or supports_tools):
        from apps.ai.tools.registry import default_toolset

        toolset = default_toolset()
        tools = toolset.anthropic_tools() if provider_name == "claude" else toolset.openai_tools()

    if provider_name != "claude":
        return tools, 0, ""

    thinking_budget = 0
    if getattr(profile, "enable_thinking", False):
        thinking_budget = int(getattr(profile, "thinking_budget", 0) or 0)
    memory_dir = ""
    if getattr(profile, "enable_memory", False):
        from apps.ai.memory import memory_dir_for_profile

        memory_dir = memory_dir_for_profile(profile_id=profile.id)
    return tools, thinking_budget, memory_dir


def _build_request(
    thread: Thread,
    user_msg: Message,
    *,
    provider_name: str = "claude",
    supports_tools: bool = False,
) -> RunRequest:
    system = thread.profile.style if thread.profile else ""
    history = _history_messages(thread)
    chat_messages: list[ChatMessage] = [
        ChatMessage(
            role=cast(RoleType, m.role),
            content=_message_content(m, provider_name=provider_name),
        )
        for m in history
    ]
    if not any(m.id == user_msg.id for m in history):
        chat_messages.append(
            ChatMessage(
                role="user",
                content=_message_content(user_msg, provider_name=provider_name),
            )
        )
    tools, thinking_budget, memory_dir = _resolve_capabilities(
        thread, provider_name=provider_name, supports_tools=supports_tools
    )
    return RunRequest(
        model="",
        system=system,
        messages=chat_messages,
        cache_system=True,
        cache_last_message=len(chat_messages) > 1,
        tools=tools,
        thinking_budget=thinking_budget,
        memory_dir=memory_dir,
    )
