"""Beat task: run the offline eval harness on a schedule (opt-in, cost-capped).

OFF by default (AIEVAL_SCHEDULED_ENABLED). When on, it replays labeled theses
through the real model, scores calibration, and persists an EvalRun the live
coach reads. Guarded by the same cost-cap pre-flight as the manual command.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.ai.cost import CostCapExceededError
from apps.analytics.services.aieval import (
    DEFAULT_EVAL_SYSTEM,
    evaluate,
    persist_eval_run,
    preflight_cost_cap,
)

log = logging.getLogger(__name__)


def _redis():
    import redis
    from django.conf import settings

    return redis.Redis.from_url(settings.REDIS_URL)


@shared_task(name="analytics.calibration_drift_sentinel")
def calibration_drift_sentinel() -> dict:
    """Daily: notify when a model's calibration newly drifts. Opt-in
    (CALIBRATION_DRIFT_SENTINEL_ENABLED, default OFF). Idempotent via a per-model
    Redis marker — alerts ONCE per drift episode and re-arms on recovery, so a
    persistent drift never spams. Reads EvalRuns only; no AI spend."""
    from django.conf import settings

    if not getattr(settings, "CALIBRATION_DRIFT_SENTINEL_ENABLED", False):
        return {"skipped": "disabled"}

    from apps.analytics.services.calibration_drift import calibration_drift
    from apps.observer.services.notifications import notify

    r = _redis()
    result = calibration_drift()
    fired = 0
    for m in result["models"]:
        key = f"caldrift:fired:{m['model']}"
        if m["drifting"]:
            if r.set(key, "1", nx=True, ex=86400):  # first detection this episode
                notify(
                    user_id=None,
                    kind="cal_drift",
                    title=f"Calibration drift: {m['model']}",
                    body=(
                        f"{m['model']} looks {m['direction']} — calibration error "
                        f"{m['baseline_error']}→{m['recent_error']}."
                    ),
                    link="/scorecard",
                )
                fired += 1
        else:
            r.delete(key)  # recovered → re-arm for a future drift
    return {"checked": len(result["models"]), "fired": fired}


@shared_task(name="analytics.aieval_run_scheduled")
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
        log.warning("analytics.aieval_run_scheduled skipped — cost cap: %s", exc)
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
        "analytics.aieval_run_scheduled persisted EvalRun #%s (n=%s, hit_rate=%s)",
        run.id,
        res["n"],
        res["hit_rate"],
    )
    return {"ran": run.id, "n": res["n"], "hit_rate": res["hit_rate"]}
