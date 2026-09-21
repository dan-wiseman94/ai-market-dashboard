"""Analytics Celery tasks: the calibration-drift sentinel and the eval harness.

The harness runs two ways — ``analytics.aieval_run_scheduled`` on beat and
``analytics.aieval_run`` queued from POST /api/aieval/runs/. Both replay labeled
theses through the real model, score calibration, and persist an EvalRun the live
coach and the calibration-weighted router read, so both sit behind the same
cost-cap pre-flight as ``manage.py aieval``.
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


@shared_task(name="analytics.aieval_run", acks_late=False, reject_on_worker_lost=False)
def aieval_run(
    *,
    provider: str,
    model: str,
    horizon: int | None,
    limit: int,
    label: str = "manual",
    system: str | None = None,
) -> dict:
    """One manual eval run queued by ``POST /api/aieval/runs/``.

    At-most-once: it bills a provider and is not idempotent, so a worker crash must
    not redeliver it. Every exit notifies, because the UI has no other signal that a
    queued run finished. The request path resolves every parameter and refuses up
    front on mock mode or a breached cap; the cap is re-checked here because spend
    can cross the line between enqueue and execution.
    """
    from apps.market.services.safe_log import scrub_secret_params
    from apps.observer.services.notifications import notify

    try:
        preflight_cost_cap(provider)
    except CostCapExceededError as exc:
        log.warning("analytics.aieval_run skipped — cost cap: %s", exc)
        notify(
            user_id=None,
            kind="eval_done",
            title="Eval run skipped",
            body=str(exc),
            link="/scorecard",
        )
        return {"skipped": "cost_cap"}

    try:
        res = evaluate(
            system=system or DEFAULT_EVAL_SYSTEM,
            model=model,
            label=label,
            horizon=horizon,
            limit=limit,
            provider=provider,
        )
    except Exception as exc:
        notify(
            user_id=None,
            kind="error",
            title="Eval run failed",
            body=scrub_secret_params(str(exc))[:500],
            link="/scorecard",
        )
        raise

    if not res["n"]:
        span = f"{horizon}d" if horizon is not None else "any horizon"
        notify(
            user_id=None,
            kind="eval_done",
            title="Eval run: nothing to replay",
            body=f"No decisive post-mortems with a frozen snapshot at {span}.",
            link="/scorecard",
        )
        return {"skipped": "no_data"}

    run = persist_eval_run(res, source="manual")
    hit = res.get("hit_rate")
    hit_txt = f"hit-rate {hit:.0%}" if hit is not None else "no scored rows"
    notify(
        user_id=None,
        kind="eval_done",
        title=f"Eval run #{run.id} finished",
        body=f"{provider} · {model}: {hit_txt} over {res['scored']} scored ({label}).",
        link="/scorecard",
    )
    return {"ran": run.id, "n": res["n"], "hit_rate": hit}


# acks_late=False for the same reason as the manual twin: one billed model call per
# labeled row plus an unconditional EvalRun append, so a redelivery after a worker
# loss would re-bill the whole replay and store a duplicate run. At-most-once turns
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
    from cryptography.fernet import InvalidToken

    from apps.ai.structured import resolve_structured_target

    provider = rc.aieval_scheduled_provider or "claude"
    # Resolve through the provider's own config: it repairs a model id carried over
    # from another vendor AND supplies the model for `local`, which has no catalog
    # default. A blank model would otherwise make every replay fail and report "no data".
    try:
        target = resolve_structured_target(
            override_provider=provider, override_model=rc.aieval_scheduled_model
        )
    except InvalidToken:
        log.warning("analytics.aieval_run_scheduled skipped — %s key is undecryptable", provider)
        return {"skipped": "undecryptable_key"}
    if target is None:
        log.warning(
            "analytics.aieval_run_scheduled skipped — no usable %s provider/model", provider
        )
        return {"skipped": "no_provider"}
    model = target.model
    horizon = rc.aieval_scheduled_horizon
    limit = rc.aieval_scheduled_limit

    try:
        preflight_cost_cap(provider)
    except CostCapExceededError as exc:
        log.warning("analytics.aieval_run_scheduled skipped — cost cap: %s", exc)
        return {"skipped": "cost_cap"}

    res = evaluate(
        system=DEFAULT_EVAL_SYSTEM,
        model=model,
        label="scheduled",
        horizon=horizon,
        limit=limit,
        provider=provider,
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
