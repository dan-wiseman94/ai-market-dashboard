"""Synchronous per-anomaly investigation via run_structured (Claude-only v1). The
full M14 agentic tool-loop is a v2 upgrade. Returns {finding, suggested_actions}
or None when the AI can't run."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured

log = logging.getLogger(__name__)


class Finding(BaseModel):
    summary: str = Field(description="What the anomaly is, in one or two sentences.")
    implication: str = Field(description="What it implies for our view; observational only.")
    suggested_actions: list[str] = Field(default_factory=list, description="1-3 concrete next steps.")


def _prompt(cand: dict) -> str:
    return (
        f"An automated sweep flagged this anomaly:\n"
        f"- type: {cand.get('anomaly_type')}\n- ticker: {cand.get('ticker') or '(book-wide)'}\n"
        f"- evidence: {cand.get('evidence')}\n\n"
        "Investigate: what is it, what does it imply for our view, and what (if anything) "
        "is worth doing? Strictly observational; no buy/sell directive."
    )


def investigate(cand: dict) -> dict | None:
    from apps.secrets.models import ProviderConfig

    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
        if cfg is None or not cfg.api_key:
            return None
        check_daily_cap("claude", cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap("claude", cap_usd=cfg.monthly_cost_cap_usd)
        f = run_structured(
            api_key=cfg.api_key, model=cfg.default_model or "claude-opus-4-8",
            system="", user=_prompt(cand), output_model=Finding, base_url=cfg.base_url or "",
        )
        finding = f"{f.summary} {f.implication}".strip()
        actions = [{"type": "suggestion", "label": s} for s in (f.suggested_actions or [])]
        subj = cand.get("ticker") or "the book"
        actions.insert(0, {"type": "convene_warroom", "label": f"Convene War Room on {subj}",
                           "params": {"free_prompt": f"Debate: {finding}"}})
        return {"finding": finding, "suggested_actions": actions}
    except CostCapExceededError as exc:
        log.warning("desk.investigate.cap_hit: %s", exc)
        return None
    except Exception:
        log.warning("desk.investigate.failed", exc_info=True)
        return None
