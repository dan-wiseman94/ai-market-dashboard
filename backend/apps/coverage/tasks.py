"""Celery tasks for coverage (M14 F3).

Registered EXPLICITLY in config/celery.py's autodiscover_tasks list (this
project does not autodiscover) — worker/beat must be restarted to register a new
task. See CLAUDE.md.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.coverage.services.revise import revise_coverage

log = logging.getLogger(__name__)


@shared_task(name="coverage.revise_from_observation")
def revise_from_observation(ticker: str, snapshot_id: int) -> None:
    """Re-run the house view for ``ticker`` against snapshot ``snapshot_id``.

    Dispatched by the observer hook after a fire on an already-covered ticker.
    ``revise_coverage`` is best-effort (returns None, never raises), so this task
    is a thin, safe wrapper that only guards against the snapshot having been
    pruned between dispatch and execution.
    """
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.filter(id=snapshot_id).first()
    if snap is None:
        log.info("coverage.revise_from_observation: snapshot %s gone, skipping", snapshot_id)
        return
    revise_coverage(ticker, snap, profile=snap.profile)
