"""Beat-scheduled poller for open Messages Batches."""
from __future__ import annotations

import logging

from celery import shared_task

from apps.observer.models import ObserverSchedule
from apps.observer.services.batch import poll_batch

log = logging.getLogger(__name__)


@shared_task(name="observer.poll_open_batches")
def poll_open_batches() -> int:
    """Every minute (via beat): poll any schedule with a pending batch id."""
    total = 0
    for sched in ObserverSchedule.objects.filter(use_batch=True).exclude(last_batch_id=""):
        try:
            moved = poll_batch(sched.id, sched.last_batch_id)
            total += moved
            if moved > 0:
                # Clear batch id so the next fire issues a fresh one.
                ObserverSchedule.objects.filter(id=sched.id).update(last_batch_id="")
        except Exception as exc:
            log.exception("poll_open_batches: schedule %s failed: %s", sched.id, exc)
    return total
