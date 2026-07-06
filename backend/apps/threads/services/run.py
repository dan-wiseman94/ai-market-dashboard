"""Service-layer form of the AI run.

``run_ai`` is the plain-callable entrypoint for a SYNCHRONOUS AI run from other
apps (war-room personas, desk investigations): identical behavior and return
contract to the ``threads.run_ai_on_message`` Celery task, without task
semantics (no queue, no E2E scenario wrapper). The returned dict carries
``message_id`` — the assistant Message this run produced (also present on the
failure paths that write a failed Message) — so callers use it directly instead
of scraping the thread by ordering.
"""

from __future__ import annotations

from apps.threads.tasks import _run_ai_on_message


def run_ai(
    *,
    thread_id: int,
    user_message_id: int,
    override: dict | None = None,
    parent_message_id: int | None = None,
    investigate: bool = False,
) -> dict:
    """Run the AI on ``user_message_id`` synchronously.

    Returns ``{"ok": bool, "error"?: str, "message_id"?: int}`` where
    ``message_id`` is the assistant Message the run created.
    """
    return _run_ai_on_message(
        thread_id=thread_id,
        user_message_id=user_message_id,
        override=override,
        parent_message_id=parent_message_id,
        investigate=investigate,
    )
