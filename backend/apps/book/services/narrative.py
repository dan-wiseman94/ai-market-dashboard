"""Best-effort one-paragraph book-risk synthesis (Claude). NEVER raises; "" on
non-claude / no key / cap / any error."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.catalog import DEFAULT_CLAUDE_MODEL
from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured

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
    from apps.secrets.models import ProviderConfig

    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
        if cfg is None or not cfg.api_key:
            return ""
        check_daily_cap("claude", cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap("claude", cap_usd=cfg.monthly_cost_cap_usd)
        report = run_structured(
            api_key=cfg.api_key,
            model=cfg.default_model or DEFAULT_CLAUDE_MODEL,
            system="",
            user=_prompt(data),
            output_model=BookNarrative,
            base_url=cfg.base_url or "",
        )
        return (getattr(report, "summary", "") or "").strip()
    except CostCapExceededError as exc:
        log.warning("book.narrative.cap_hit: %s", exc)
        return ""
    except Exception:
        log.warning("book.narrative.failed", exc_info=True)
        return ""
