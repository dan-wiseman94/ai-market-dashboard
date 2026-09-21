"""Best-effort one-paragraph regime narrative (structured output on the default
provider). NEVER raises; returns "" on no usable provider / cap hit / any
provider error — the deterministic axes + composite are already persisted by
the caller."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from apps.ai.cost import CostCapExceededError
from apps.ai.structured import ensure_within_caps, resolve_structured_target, run_structured
from apps.core.runtime_config import runtime_config

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
    if not runtime_config().regime_narrative_enabled:
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
            user=_build_prompt(composite, axes, drivers),
            output_model=RegimeNarrative,
            base_url=target.base_url,
        )
        return (getattr(report, "summary", "") or "").strip()
    except CostCapExceededError as exc:
        log.warning("regime.narrative.cap_hit: %s", exc)
        return ""
    except Exception:
        log.warning("regime.narrative.failed", exc_info=True)
        return ""
