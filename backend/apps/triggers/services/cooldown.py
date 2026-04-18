"""Cooldown gate: both time-elapsed AND re-armed-on-false must pass."""
from __future__ import annotations

import redis
from django.conf import settings
from django.utils import timezone

from apps.triggers.models import EventTrigger

ARMED_KEY = "trigger:armed:{trigger_id}"
ARMED_TTL_SECONDS = 86400  # 1 day — long enough to survive overnight


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def cooldown_blocks(trigger: EventTrigger) -> bool:
    """True when we should skip firing this trigger on the current tick."""
    if trigger.last_fired_at is None:
        return False
    elapsed = (timezone.now() - trigger.last_fired_at).total_seconds()
    if elapsed < trigger.cooldown_seconds:
        return True
    # Time elapsed → require the re-arm flag (condition went False since last fire)
    return not _redis().exists(ARMED_KEY.format(trigger_id=trigger.id))


def mark_fired(trigger_id: int) -> None:
    """Called when the trigger fires — clears the re-armed flag."""
    _redis().delete(ARMED_KEY.format(trigger_id=trigger_id))


def mark_rearmed(trigger_id: int) -> None:
    """Called when the condition evaluates False — allows next fire once cooldown elapses."""
    _redis().setex(ARMED_KEY.format(trigger_id=trigger_id), ARMED_TTL_SECONDS, "1")
