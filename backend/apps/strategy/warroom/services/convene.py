"""Orchestrate a War Room debate: thin convene() dispatches to run_debate task.
Personas -> (rebuttal) -> verdict logic lives in apps.strategy.tasks."""

from __future__ import annotations

import logging

from apps.ai.catalog import DEFAULT_CLAUDE_MODEL
from apps.strategy.models import WarRoomRun
from apps.strategy.warroom import constants as C
from apps.strategy.warroom.services.subject import subject_context

log = logging.getLogger(__name__)


def _claude_cfg():
    """Return (api_key, model, base_url) for claude, cap-checked, or None."""
    from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
    from apps.secrets.models import ProviderConfig

    try:
        cfg = ProviderConfig.objects.filter(provider="claude").first()
        if cfg is None or not cfg.api_key:
            return None
        check_daily_cap("claude", cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap("claude", cap_usd=cfg.monthly_cost_cap_usd)
        return cfg.api_key, (cfg.default_model or DEFAULT_CLAUDE_MODEL), (cfg.base_url or "")
    except CostCapExceededError as exc:
        log.warning("warroom.cap_hit: %s", exc)
        return None
    except Exception:
        log.warning("warroom.cfg_failed", exc_info=True)
        return None


def convene(
    *,
    thesis=None,
    coverage_note=None,
    book_snapshot=None,
    free_prompt="",
    structure=C.DEFAULT_STRUCTURE,
    voice_mode="single",
    grounding=True,
) -> WarRoomRun:
    from apps.strategy.tasks import run_debate
    from apps.threads.models import Thread

    label, _ctx = subject_context(
        thesis=thesis,
        coverage_note=coverage_note,
        book_snapshot=book_snapshot,
        free_prompt=free_prompt,
    )
    subject_kind = (
        "thesis" if thesis else "coverage" if coverage_note else "book" if book_snapshot else "free"
    )
    thread = Thread.objects.create(kind="warroom", title=f"Debate: {label}"[:200])
    run = WarRoomRun.objects.create(
        thread=thread,
        subject_kind=subject_kind,
        subject_label=label,
        thesis=thesis,
        coverage_note=coverage_note,
        book_snapshot=book_snapshot,
        free_prompt=free_prompt,
        params={"structure": structure, "voice_mode": voice_mode, "grounding": grounding},
        status="running",
    )
    run_debate.delay(run.id)
    return run
