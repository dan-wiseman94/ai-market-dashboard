from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings

from apps.desk.services.sweep import run_sweep

log = logging.getLogger(__name__)


@shared_task(name="desk.sweep")
def sweep() -> int | None:
    """Opt-in (ANOMALY_SWEEP_ENABLED, default OFF — autonomy that spends money)."""
    if not getattr(settings, "ANOMALY_SWEEP_ENABLED", False):
        log.info("desk.sweep: disabled (ANOMALY_SWEEP_ENABLED off)")
        return None
    return run_sweep()
