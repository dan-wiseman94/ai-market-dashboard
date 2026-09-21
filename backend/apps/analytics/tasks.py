"""Analytics Celery tasks: the calibration-drift sentinel and the eval harness.

The harness runs two ways — ``analytics.aieval_run_scheduled`` on beat and
``analytics.aieval_run_manual`` queued from POST /api/aieval/runs/. Both replay
labeled theses through the real model, score calibration, and persist an EvalRun
the live coach and the calibration-weighted router read, so both sit behind the
same cost-cap pre-flight as ``manage.py aieval``.
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
    """Daily: notify when a model's calibration newly drifts. Toggleable from the UI
    (SystemSettings.calibration_drift_sentinel_enabled, else
    CALIBRATION_DRIFT_SENTINEL_ENABLED). Idempotent via a per-model Redis marker —
    alerts ONCE per drift episode and re-arms on recovery, so a persistent drift never
    spams. Reads EvalRuns only; no AI spend."""
    from apps.core.runtime_config import runtime_config

    if not runtime_config().calibration_drift_sentinel_enabled:
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


# acks_late=False: evaluate() bills one model call per labeled row and
# persist_eval_run() appends unconditionally, so a redelivery after a worker loss
# would re-bill the whole replay and store a duplicate EvalRun. At-most-once turns
# a lost run into a missing result the user can re-trigger.
@shared_task(name="analytics.aieval_run_scheduled", acks_late=False, reject_on_worker_lost=False)
def run_scheduled() -> dict:
    from apps.core.mocks import is_mock_mode
    from apps.core.runtime_config import runtime_config

    # evaluate() reaches the provider through run_structured, which has NO
    # MOCK_EXTERNAL short-circuit — so under the e2e overlay an armed schedule would
    # bill a real model call. Refuse before any provider work. The manual path
    # (`manage.py aieval`) calls evaluate() directly and is deliberately untouched.
    if is_mock_mode():
        log.info("analytics.aieval_run_scheduled skipped — MOCK_EXTERNAL")
        return {"skipped": "mock_mode"}

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
        provider="claude",
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


# acks_late=False for the same reason as the scheduled twin: one billed model call
# per labeled row plus an unconditional EvalRun append.
@shared_task(name="analytics.aieval_run_manual", acks_late=False, reject_on_worker_lost=False)
def run_manual(
    *,
    model: str,
    provider: str,
    label: str,
    horizon: int | None = None,
    limit: int | None = None,
    system: str | None = None,
) -> dict:
    """On-demand eval queued from POST /api/aieval/runs/.

    The request path resolves every parameter and refuses up front on mock mode or a
    breached cap, so the caller sees the reason. The cap is re-checked here because
    spend can cross the line between enqueue and execution.
    """
    try:
        preflight_cost_cap(provider)
    except CostCapExceededError as exc:
        log.warning("analytics.aieval_run_manual skipped — cost cap: %s", exc)
        return {"skipped": "cost_cap"}

    res = evaluate(
        system=system or DEFAULT_EVAL_SYSTEM,
        model=model,
        label=label,
        horizon=horizon,
        limit=limit,
        provider=provider,
    )
    if not res["n"]:
        return {"skipped": "no_data"}

    run = persist_eval_run(res, source="manual")
    log.info(
        "analytics.aieval_run_manual persisted EvalRun #%s (n=%s, hit_rate=%s)",
        run.id,
        res["n"],
        res["hit_rate"],
    )
    return {"ran": run.id, "n": res["n"], "hit_rate": res["hit_rate"]}
