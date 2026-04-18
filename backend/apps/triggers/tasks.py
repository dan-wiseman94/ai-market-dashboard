"""Celery tasks for the trigger evaluator and fire path."""
from __future__ import annotations

import time

import structlog
from celery import shared_task

from apps.observer.services.market_hours import is_market_open
from apps.triggers import evaluator, metrics
from apps.triggers.models import EventTrigger
from apps.triggers.services.cooldown import cooldown_blocks, mark_fired, mark_rearmed

logger = structlog.get_logger(__name__)


@shared_task(name="triggers.evaluate_triggers")
def evaluate_triggers() -> dict:
    """Beat-scheduled tick. Fires matching triggers; returns a summary for logs."""
    if not is_market_open():
        logger.debug("trigger.tick.market_closed")
        return {"evaluated": 0, "fires": 0, "skipped": "market_closed"}

    t0 = time.perf_counter()
    triggers = list(
        EventTrigger.objects.filter(enabled=True).select_related("profile"),
    )
    if not triggers:
        return {"evaluated": 0, "fires": 0}

    snapshot = metrics.build_snapshot(triggers)
    fires = 0
    for trigger in triggers:
        try:
            if cooldown_blocks(trigger):
                continue
            matched, values = evaluator.evaluate(trigger.condition, snapshot)
        except Exception as exc:
            logger.error(
                "trigger.evaluate.failed",
                trigger_id=trigger.id, trigger_name=trigger.name, error=str(exc),
            )
            _disable_on_bad_condition(trigger, exc)
            continue

        if not matched:
            mark_rearmed(trigger.id)
            continue
        mark_fired(trigger.id)
        fire_trigger.delay(trigger_id=trigger.id, matched_values=values)
        fires += 1

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "trigger.tick",
        triggers_evaluated=len(triggers), fires_enqueued=fires,
        duration_ms=duration_ms,
    )
    return {"evaluated": len(triggers), "fires": fires, "duration_ms": duration_ms}


def _disable_on_bad_condition(trigger: EventTrigger, exc: Exception) -> None:
    trigger.enabled = False
    trigger.save(update_fields=["enabled", "updated_at"])
    logger.error(
        "trigger.disabled.invalid_condition",
        trigger_id=trigger.id, error=str(exc),
    )


@shared_task(name="triggers.fire_trigger", autoretry_for=(), max_retries=0)
def fire_trigger(trigger_id: int, matched_values: dict) -> None:
    """Placeholder — fully implemented in Task 13."""
    raise NotImplementedError
