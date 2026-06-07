"""Celery tasks for the trigger evaluator and fire path."""

from __future__ import annotations

import time

import redis
import structlog
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.ai.cost import CostCapExceededError, check_daily_cap, check_monthly_cap
from apps.market.calendar import any_market_open
from apps.observer.models import EventTrigger, TriggerFiring
from apps.observer.services.notifications import notify
from apps.observer.triggers import evaluator, metrics
from apps.observer.triggers.dsl import tickers_in_condition
from apps.observer.triggers.services.cooldown import cooldown_blocks, mark_fired, mark_rearmed
from apps.observer.triggers.services.describe import describe
from apps.secrets.models import ProviderConfig
from apps.snapshots.serializer import serialize_for_ai
from apps.snapshots.services import capture
from apps.threads.models import Message, Thread
from apps.threads.tasks import run_ai_on_message

logger = structlog.get_logger(__name__)

FIRE_LOCK_KEY = "trigger:fire:{trigger_id}"
FIRE_LOCK_TTL = 60


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


@shared_task(name="triggers.evaluate_triggers")
def evaluate_triggers() -> dict:
    """Beat-scheduled tick. Fires matching triggers; returns a summary for logs."""
    t0 = time.perf_counter()
    triggers = list(
        EventTrigger.objects.filter(enabled=True).select_related("profile"),
    )
    if not triggers:
        return {"evaluated": 0, "fires": 0}

    live = [t for t in triggers if any_market_open(tickers_in_condition(t.condition))]
    if not live:
        logger.debug("trigger.tick.all_markets_closed")
        return {"evaluated": 0, "fires": 0, "skipped": "all_markets_closed"}

    snapshot = metrics.build_snapshot(live)
    fires = 0
    for trigger in live:
        try:
            if cooldown_blocks(trigger):
                continue
            matched, values = evaluator.evaluate(trigger.condition, snapshot)
        except Exception as exc:
            logger.error(
                "trigger.evaluate.failed",
                trigger_id=trigger.id,
                trigger_name=trigger.name,
                error=str(exc),
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
        triggers_evaluated=len(live),
        fires_enqueued=fires,
        duration_ms=duration_ms,
    )
    return {"evaluated": len(live), "fires": fires, "duration_ms": duration_ms}


def _disable_on_bad_condition(trigger: EventTrigger, exc: Exception) -> None:
    trigger.enabled = False
    trigger.save(update_fields=["enabled", "updated_at"])
    logger.error(
        "trigger.disabled.invalid_condition",
        trigger_id=trigger.id,
        error=str(exc),
    )


@shared_task(name="triggers.fire_trigger", autoretry_for=(), max_retries=0)
def fire_trigger(trigger_id: int, matched_values: dict) -> None:
    """Run the full fire path for one trigger. Never retried (would double-fire)."""
    r = _redis()
    lock_key = FIRE_LOCK_KEY.format(trigger_id=trigger_id)
    # SET NX with TTL acts as a mutex. If the key already exists, skip.
    if not r.set(lock_key, "1", nx=True, ex=FIRE_LOCK_TTL):
        logger.warning("trigger.fire.already_running", trigger_id=trigger_id)
        return
    try:
        _do_fire(trigger_id=trigger_id, matched_values=matched_values)
    finally:
        r.delete(lock_key)


def _do_fire(*, trigger_id: int, matched_values: dict) -> None:
    trigger = EventTrigger.objects.select_related("profile").get(id=trigger_id)
    firing = TriggerFiring.objects.create(
        trigger=trigger,
        matched_values=matched_values,
    )
    trigger.last_fired_at = timezone.now()
    trigger.save(update_fields=["last_fired_at", "updated_at"])

    try:
        snap = capture(
            profile=trigger.profile,
            objective=f"Triggered: {trigger.name}",
            includes=trigger.profile.default_includes,
            source="trigger",
        )
    except Exception as exc:
        logger.error(
            "trigger.fire.capture_failed",
            trigger_id=trigger.id,
            error=str(exc),
        )
        notify(
            user_id=None,
            kind="error",
            title=f"{trigger.name} fired — snapshot failed",
            body=str(exc),
            link=f"/triggers/{trigger.id}",
        )
        return

    firing.snapshot = snap
    firing.save(update_fields=["snapshot"])

    # Cost-cap check: expensive part is the AI run, not the snapshot.
    provider_name = trigger.profile.default_provider
    try:
        # defer the encrypted key: only cap fields are read (the AI call delegates to
        # run_ai_on_message), so an undecryptable key/salt rotation can't crash the fire.
        cfg = ProviderConfig.objects.defer("_api_key").get(provider=provider_name)
        check_daily_cap(provider_name, cap_usd=cfg.daily_cost_cap_usd)
        check_monthly_cap(provider_name, cap_usd=cfg.monthly_cost_cap_usd)
    except ProviderConfig.DoesNotExist:
        logger.warning(
            "trigger.fire.no_provider_config",
            trigger_id=trigger.id,
            provider=provider_name,
        )
        # No config → no cap enforcement; proceed to AI run.
    except CostCapExceededError as exc:
        firing.cost_capped = True
        firing.save(update_fields=["cost_capped"])
        notify(
            user_id=None,
            kind="cost_limit",
            title=f"{trigger.name} fired — AI skipped (cap hit)",
            body=f"{describe(matched_values)} · {exc}",
            link=f"/triggers/{trigger.id}",
        )
        logger.info(
            "trigger.fire.ai_skipped_cost_capped",
            trigger_id=trigger.id,
            provider=provider_name,
        )
        return

    thread = Thread.objects.create(
        kind="chat",
        profile=trigger.profile,
        pinned_snapshot=snap,
        title=f"{trigger.name} fired at {timezone.localtime():%H:%M}",
    )
    firing.thread = thread
    firing.save(update_fields=["thread"])

    from apps.threads.coach import assemble_coach_context

    coach = assemble_coach_context(snap, trigger.profile)
    text = serialize_for_ai(snap, provider=provider_name, model=trigger.profile.default_model)
    user_msg = Message.objects.create(
        thread=thread,
        role="user",
        content={"text": coach + text},
        snapshot_ref=snap,
        status="done",
    )
    run_ai_on_message.delay(
        thread_id=thread.id, user_message_id=user_msg.id, investigate=trigger.investigate
    )

    notify(
        user_id=None,
        kind="trigger",
        title=trigger.name,
        body=describe(matched_values),
        link=f"/threads/{thread.id}",
    )
    logger.info(
        "trigger.fired",
        trigger_id=trigger.id,
        trigger_name=trigger.name,
        profile_id=trigger.profile_id,
        snapshot_id=snap.id,
        thread_id=thread.id,
        cost_capped=False,
    )
