"""Agentic per-anomaly investigation (M15 F4 v2). Originates a REAL bounded
investigation via the M14 tool loop (run_ai_on_message investigate=True) in a
fresh thread, then reads the assistant finding. Returns
{finding, suggested_actions, investigation_thread_id} or None when nothing was
produced (no provider / cap / error — run_ai_on_message degrades internally)."""

from __future__ import annotations

import logging

from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message

log = logging.getLogger(__name__)


def _prompt(cand: dict) -> str:
    return (
        f"An automated sweep flagged this market anomaly:\n"
        f"- type: {cand.get('anomaly_type')}\n- ticker: {cand.get('ticker') or '(book-wide)'}\n"
        f"- evidence: {cand.get('evidence')}\n\n"
        "Investigate it using your tools (quotes, news, recall, etc.): what is it, what does it "
        "imply for our view, and what (if anything) is worth doing? Strictly observational."
    )


def _thesis_direction(cand: dict) -> str:
    """A starting direction to prefill the thesis form. A price move points the way;
    everything else defaults to neutral for the user to decide."""
    if cand.get("anomaly_type") == "price_move":
        pct = (cand.get("evidence") or {}).get("pct_change") or 0
        if pct > 0:
            return "bullish"
        if pct < 0:
            return "bearish"
    return "neutral"


def investigate(cand: dict) -> dict | None:
    thread = Thread.objects.create(
        kind="consult",
        title=f"Investigation: {cand.get('anomaly_type')} {cand.get('ticker') or 'book'}"[:200],
    )
    user_msg = Message.objects.create(
        thread=thread, role="user", status="done", content={"text": _prompt(cand)}
    )
    try:
        # Synchronous (we're already inside the sweep worker); investigate=True forces the
        # bounded M14 tool loop. Degrades internally (no key / cap / error) -> no assistant msg.
        run_ai_on_message(thread_id=thread.id, user_message_id=user_msg.id, investigate=True)
    except Exception:
        log.warning("desk.investigate.run_failed", exc_info=True)

    assistant = (
        Message.objects.filter(thread=thread, role="assistant", status="done")
        .order_by("-created_at")
        .first()
    )
    if assistant is None:
        return None
    content = assistant.content if isinstance(assistant.content, dict) else {}
    finding = (content.get("text") or "").strip()
    if not finding:
        return None

    subj = cand.get("ticker") or "the book"
    actions = [
        {
            "type": "convene_warroom",
            "label": f"Convene War Room on {subj}",
            "params": {"free_prompt": f"Debate: {finding[:500]}"},
        },
    ]
    if cand.get("ticker"):
        actions.append(
            {
                "type": "revise_coverage",
                "label": f"Revise coverage on {cand['ticker']}",
                "params": {"ticker": cand["ticker"]},
            }
        )
        actions.append(
            {
                "type": "open_thesis",
                "label": f"Open thesis on {cand['ticker']}",
                # A deep link prefills the new-thesis form; the user still supplies the
                # invalidation (C4 pre-trade discipline) before it can be saved.
                "params": {
                    "ticker": cand["ticker"],
                    "direction": _thesis_direction(cand),
                    "rationale": finding[:500],
                },
            }
        )
    return {"finding": finding, "suggested_actions": actions, "investigation_thread_id": thread.id}
