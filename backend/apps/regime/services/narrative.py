"""Best-effort one-paragraph regime narrative (Claude). NEVER raises; returns ""
on non-claude / no key / cap hit / any provider error — the deterministic axes +
composite are already persisted by the caller."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.ai.providers.claude_structured import run_structured

log = logging.getLogger(__name__)


class RegimeNarrative(BaseModel):
    summary: str = Field(description="One tight paragraph naming the regime and its 2-3 drivers.")


def _build_prompt(composite: str, axes: dict, drivers: list[str]) -> str:
    axes_lines = "\n".join(f"- {k}: {v}" for k, v in axes.items())
    return (
        f"Current market regime composite: {composite}.\n\nAxes:\n{axes_lines}\n\n"
        f"Drivers: {', '.join(drivers) or 'n/a'}.\n\n"
        "Write ONE tight paragraph (<=4 sentences) naming the regime and its key drivers. "
        "Strictly observational; no buy/sell advice."
    )


def regime_narrative(composite: str, axes: dict, drivers: list[str]) -> str:
    from apps.secrets.models import ProviderConfig

    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
        if cfg is None or not cfg.api_key:
            return ""
        check_daily_cap("claude", cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap("claude", cap_usd=cfg.monthly_cost_cap_usd)
        report = run_structured(
            api_key=cfg.api_key,
            model=cfg.default_model or "claude-opus-4-8",
            system="",
            user=_build_prompt(composite, axes, drivers),
            output_model=RegimeNarrative,
            base_url=cfg.base_url or "",
        )
        return (getattr(report, "summary", "") or "").strip()
    except CostCapExceededError as exc:
        log.warning("regime.narrative.cap_hit: %s", exc)
        return ""
    except Exception:
        log.warning("regime.narrative.failed", exc_info=True)
        return ""
