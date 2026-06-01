from __future__ import annotations

import logging

from celery import shared_task

from apps.observer.services.market_hours import is_market_open
from apps.regime.services.compute import compute_and_store

log = logging.getLogger(__name__)


@shared_task(name="regime.refresh")
def refresh(force: bool = False) -> int | None:
    """Compute + persist one RegimeReading. Skips when the market is closed unless
    ``force`` (the pre-open / post-close forced readings pass force=True)."""
    if not force and not is_market_open():
        log.info("regime.refresh: market closed, skipping")
        return None
    reading = compute_and_store()
    return reading.id
