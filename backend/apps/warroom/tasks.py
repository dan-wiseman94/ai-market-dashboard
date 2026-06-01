from __future__ import annotations

import logging

from celery import shared_task

from apps.threads.models import Message
from apps.warroom import constants as C
from apps.warroom.models import WarRoomRun
from apps.warroom.services.convene import _claude_cfg
from apps.warroom.services.debate import run_one_persona
from apps.warroom.services.subject import subject_context
from apps.warroom.services.verdict import synthesize
from apps.warroom.services.voices import assign_voices

log = logging.getLogger(__name__)


@shared_task(name="warroom.run_debate")
def run_debate(run_id: int) -> None:
    run = WarRoomRun.objects.filter(id=run_id).first()
    if run is None:
        return
    _label, ctx = subject_context(
        thesis=run.thesis,
        coverage_note=run.coverage_note,
        book_snapshot=run.book_snapshot,
        free_prompt=run.free_prompt,
    )
    voices = assign_voices(run.params.get("voice_mode", "single"))
    if all(not prov for _p, prov, _m in voices):
        run.status = "error"
        run.error = "No enabled provider configured."
        run.save(update_fields=["status", "error"])
        return

    grounding = bool(run.params.get("grounding", True))
    structure = run.params.get("structure", C.DEFAULT_STRUCTURE)
    rounds = C.DEEP_MAX_ROUNDS if structure == "deep" else (1 if structure == "rebuttal" else 0)

    persona_args: list[dict] = []
    for r in range(rounds + 1):
        prior = list(persona_args) if r > 0 else []
        round_args = []
        for persona, provider, model in voices:
            arg = run_one_persona(
                run.thread, persona, ctx, prior, provider=provider, model=model, grounding=grounding
            )
            if arg:
                round_args.append(arg)
        if round_args:
            persona_args = round_args

    cfg = _claude_cfg()
    if cfg is None or not persona_args:
        run.status = "error"
        run.error = "Debate produced no arguments / no Claude key for synthesis."
        run.save(update_fields=["status", "error"])
        return
    api_key, model, base_url = cfg
    v = synthesize(ctx, persona_args, api_key=api_key, model=model, base_url=base_url)
    verdict = {
        "verdict": v.verdict,
        "confidence": v.confidence,
        "strongest_bull": v.strongest_bull,
        "strongest_bear": v.strongest_bear,
        "what_would_change_my_mind": v.what_would_change_my_mind,
    }
    Message.objects.create(
        thread=run.thread,
        role="assistant",
        status="done",
        content={"kind": "warroom_verdict", **verdict},
    )
    run.verdict = verdict
    run.confidence = v.confidence
    run.status = "done"
    run.save(update_fields=["verdict", "confidence", "status"])
