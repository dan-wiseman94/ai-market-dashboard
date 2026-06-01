"""Run a single persona as a real streaming run via run_ai_on_message (multi-
provider via override, tool-grounded via investigate), then stamp the persona on
the resulting assistant message so the courtroom UI can lane it."""

from __future__ import annotations

import logging

from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message
from apps.warroom.services.personas import _FRAMING, _user_prompt

log = logging.getLogger(__name__)


def run_one_persona(thread: Thread, persona: str, subject_context: str, prior_args: list[dict],
                    *, provider: str, model: str, grounding: bool) -> dict | None:
    """Returns {"persona", "argument"} or None if the run produced nothing."""
    user_text = f"{_FRAMING[persona]}\n\n{_user_prompt(subject_context, prior_args)}"
    um = Message.objects.create(thread=thread, role="user", status="done", content={"text": user_text})
    override = {"provider": provider, "model": model} if provider and model else None
    try:
        run_ai_on_message(thread_id=thread.id, user_message_id=um.id, override=override, investigate=grounding)
    except Exception:
        log.warning("warroom.persona_run_failed persona=%s", persona, exc_info=True)
    assistant = (
        Message.objects.filter(thread=thread, role="assistant", status="done").order_by("-created_at").first()
    )
    if assistant is None:
        return None
    content = assistant.content if isinstance(assistant.content, dict) else {}
    argument = (content.get("text") or "").strip()
    if not argument:
        return None
    content["persona"] = persona
    assistant.content = content
    assistant.save(update_fields=["content"])
    return {"persona": persona, "argument": argument}
