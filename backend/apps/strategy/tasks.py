"""Celery tasks for the strategy domain (merged from the former coverage / warroom /
desk apps). Registered via "apps.strategy" in config/celery.py's TASK_PACKAGES.

- ``coverage.revise_from_observation`` (queued by the observer hook) and
  ``warroom.run_debate`` (queued on convene) keep their names — they aren't beat
  tasks, so the name-prefix==owning-app guard doesn't apply and callers use the
  function reference.
- ``desk.sweep`` IS beat-scheduled, so it is renamed ``strategy.sweep`` to keep the
  registration + scheduled-work-inventory guards valid.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.strategy.coverage.services.revise import revise_coverage
from apps.strategy.desk.services.sweep import run_sweep
from apps.strategy.models import WarRoomRun
from apps.strategy.warroom import constants as C
from apps.strategy.warroom.services.convene import _claude_cfg
from apps.strategy.warroom.services.debate import run_one_persona
from apps.strategy.warroom.services.subject import subject_context
from apps.strategy.warroom.services.verdict import synthesize
from apps.strategy.warroom.services.voices import assign_voices
from apps.threads.models import Message

log = logging.getLogger(__name__)


@shared_task(name="coverage.revise_from_observation")
def revise_from_observation(ticker: str, snapshot_id: int) -> None:
    """Re-run the house view for ``ticker`` against snapshot ``snapshot_id``.

    Dispatched by the observer hook after a fire on an already-covered ticker.
    Best-effort; only guards against the snapshot being pruned between dispatch and
    execution.
    """
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(id=snapshot_id).first()
    if snap is None:
        log.info("coverage.revise_from_observation: snapshot %s gone, skipping", snapshot_id)
        return
    revise_coverage(ticker, snap, profile=snap.profile)


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


@shared_task(name="strategy.sweep")
def sweep() -> int | None:
    """Opt-in (ANOMALY_SWEEP_ENABLED, default OFF — autonomy that spends money)."""
    if not getattr(settings, "ANOMALY_SWEEP_ENABLED", False):
        log.info("desk.sweep: disabled (ANOMALY_SWEEP_ENABLED off)")
        return None
    return run_sweep()
