"""Best-effort one-paragraph book-risk synthesis (structured output on the
default provider). NEVER raises; "" on no usable provider / cap / any error."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.cost import CostCapExceededError
from apps.ai.structured import ensure_within_caps, resolve_structured_target, run_structured
from apps.core.runtime_config import runtime_config

log = logging.getLogger(__name__)


class BookNarrative(BaseModel):
    summary: str = Field(description="One tight paragraph on the book's top risk(s).")


def _prompt(data: dict) -> str:
    conc = data.get("concentration", {})
    fit = data.get("regime_fit", {})
    clusters = ", ".join("/".join(c["members"]) for c in data.get("clusters", [])) or "none"
    return (
        f"Whole-book risk X-ray.\n- Concentration: top-{len(data.get('exposures', []))} HHI "
        f"{conc.get('hhi')}, top-N share {conc.get('top_n_share')}\n"
        f"- Net long {conc.get('net_long')}, net short {conc.get('net_short')}\n"
        f"- Correlation clusters: {clusters}\n- Regime fit: {fit.get('alignment')} — {fit.get('note')}\n"
        f"- Names near their invalidation: {len(data.get('near_invalidation', []))}\n\n"
        "Write ONE tight paragraph (<=4 sentences) naming the book's single biggest risk. "
        "Strictly observational; no buy/sell advice."
    )


def book_narrative(data: dict) -> str:
    if not runtime_config().book_narrative_enabled:
        return ""
    try:
        target = resolve_structured_target()
        if target is None:
            return ""
        ensure_within_caps(target)
        report = run_structured(
            provider=target.provider,
            api_key=target.api_key,
            model=target.model,
            system="",
            user=_prompt(data),
            output_model=BookNarrative,
            base_url=target.base_url,
        )
        return (getattr(report, "summary", "") or "").strip()
    except CostCapExceededError as exc:
        log.warning("book.narrative.cap_hit: %s", exc)
        return ""
    except Exception:
        log.warning("book.narrative.failed", exc_info=True)
        return ""
