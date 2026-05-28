"""Beat task: fire the daily briefing once when due."""

from __future__ import annotations

from celery import shared_task

from apps.briefing.models import BriefingConfig
from apps.briefing.services.run import _now_local, run_briefing


@shared_task(name="briefing.run_scheduled")
def run_scheduled() -> dict:
    cfg = BriefingConfig.load()
    if not cfg.enabled:
        return {"skipped": "disabled"}
    if _now_local().time() < cfg.send_at_local:
        return {"skipped": "before_send_at"}
    run = run_briefing(scheduled=True)
    return {"ran": run.id if run else None}
