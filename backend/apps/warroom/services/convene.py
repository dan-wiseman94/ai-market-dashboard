"""Orchestrate a War Room debate: personas -> (rebuttal) -> verdict, persisted as a
kind='warroom' Thread + a WarRoomRun. Claude-only synchronous v1."""

from __future__ import annotations

import logging

from apps.threads.models import Message, Thread
from apps.warroom import constants as C
from apps.warroom.models import WarRoomRun
from apps.warroom.services.personas import run_persona
from apps.warroom.services.subject import subject_context
from apps.warroom.services.verdict import synthesize

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
        return cfg.api_key, (cfg.default_model or "claude-opus-4-8"), (cfg.base_url or "")
    except CostCapExceededError as exc:
        log.warning("warroom.cap_hit: %s", exc)
        return None
    except Exception:
        log.warning("warroom.cfg_failed", exc_info=True)
        return None


def _persist_persona(thread: Thread, persona: str, arg) -> dict:
    Message.objects.create(
        thread=thread,
        role="assistant",
        status="done",
        content={
            "persona": persona,
            "argument": arg.argument,
            "key_points": list(arg.key_points or []),
        },
    )
    return {"persona": persona, "argument": arg.argument}


def convene(
    *,
    thesis=None,
    coverage_note=None,
    book_snapshot=None,
    free_prompt: str = "",
    structure: str = C.DEFAULT_STRUCTURE,
    voice_mode: str = "single",
    grounding: bool = False,
) -> WarRoomRun:
    label, ctx = subject_context(
        thesis=thesis,
        coverage_note=coverage_note,
        book_snapshot=book_snapshot,
        free_prompt=free_prompt,
    )
    subject_kind = (
        "thesis" if thesis else "coverage" if coverage_note else "book" if book_snapshot else "free"
    )
    params = {"structure": structure, "voice_mode": voice_mode, "grounding": grounding}

    cfg = _claude_cfg()
    thread = Thread.objects.create(kind="warroom", title=f"Debate: {label}"[:200])
    Message.objects.create(thread=thread, role="user", status="done", content={"text": ctx})

    if cfg is None:
        return WarRoomRun.objects.create(
            thread=thread,
            subject_kind=subject_kind,
            subject_label=label,
            thesis=thesis,
            coverage_note=coverage_note,
            book_snapshot=book_snapshot,
            free_prompt=free_prompt,
            params=params,
            status="error",
            error="No Claude provider configured or cost cap hit.",
        )

    api_key, model, base_url = cfg
    rounds = C.DEEP_MAX_ROUNDS if structure == "deep" else (1 if structure == "rebuttal" else 0)
    persona_args: list[dict] = []
    for r in range(rounds + 1):
        prior = list(persona_args) if r > 0 else []
        round_args = []
        for persona in C.PERSONAS:
            arg = run_persona(persona, ctx, prior, api_key=api_key, model=model, base_url=base_url)
            round_args.append(_persist_persona(thread, persona, arg))
        persona_args = round_args

    v = synthesize(ctx, persona_args, api_key=api_key, model=model, base_url=base_url)
    verdict = {
        "verdict": v.verdict,
        "confidence": v.confidence,
        "strongest_bull": v.strongest_bull,
        "strongest_bear": v.strongest_bear,
        "what_would_change_my_mind": v.what_would_change_my_mind,
    }
    Message.objects.create(
        thread=thread,
        role="assistant",
        status="done",
        content={"kind": "warroom_verdict", **verdict},
    )
    return WarRoomRun.objects.create(
        thread=thread,
        subject_kind=subject_kind,
        subject_label=label,
        thesis=thesis,
        coverage_note=coverage_note,
        book_snapshot=book_snapshot,
        free_prompt=free_prompt,
        params=params,
        verdict=verdict,
        confidence=v.confidence,
        status="done",
    )
