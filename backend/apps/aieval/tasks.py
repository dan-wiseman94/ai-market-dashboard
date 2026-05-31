"""Beat task: run the offline eval harness on a schedule (opt-in, cost-capped).

OFF by default (AIEVAL_SCHEDULED_ENABLED). When on, it replays labeled theses
through the real model, scores calibration, and persists an EvalRun the live
coach (A3) reads. Guarded by the same cost-cap pre-flight as the manual command.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.ai.cost import CostCapExceededError
from apps.aieval.services import (
    DEFAULT_EVAL_SYSTEM,
    evaluate,
    persist_eval_run,
    preflight_cost_cap,
)

log = logging.getLogger(__name__)


@shared_task(name="aieval.run_scheduled")
def run_scheduled() -> dict:
    from apps.core.runtime_config import runtime_config

    rc = runtime_config()
    if not rc.aieval_scheduled_enabled:
        return {"skipped": "disabled"}

    # SystemSettings (UI) values override the base.py / env defaults; the resolver's
    # fallbacks keep this a BOUNDED run (25 rows / 30d horizon), never an unbounded —
    # and costly — replay.
    model = rc.aieval_scheduled_model
    horizon = rc.aieval_scheduled_horizon
    limit = rc.aieval_scheduled_limit

    try:
        preflight_cost_cap("claude")
    except CostCapExceededError as exc:
        log.warning("aieval.run_scheduled skipped — cost cap: %s", exc)
        return {"skipped": "cost_cap"}

    res = evaluate(
        system=DEFAULT_EVAL_SYSTEM,
        model=model,
        label="scheduled",
        horizon=horizon,
        limit=limit,
    )
    if not res["n"]:
        return {"skipped": "no_data"}

    run = persist_eval_run(res, source="scheduled")
    log.info(
        "aieval.run_scheduled persisted EvalRun #%s (n=%s, hit_rate=%s)",
        run.id,
        res["n"],
        res["hit_rate"],
    )
    return {"ran": run.id, "n": res["n"], "hit_rate": res["hit_rate"]}
