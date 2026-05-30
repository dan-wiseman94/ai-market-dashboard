"""Core app signal handlers.

Imported by CoreConfig.ready() so signal connections are registered once
the Django app registry is ready.
"""

from __future__ import annotations

import logging

from celery.signals import task_failure

logger = logging.getLogger(__name__)


@task_failure.connect
def _on_task_failure(
    sender=None,
    task_id=None,
    exception=None,
    traceback=None,
    einfo=None,
    **kw,
) -> None:
    """Persist an ErrorEvent whenever any Celery task fails.

    Never raises — a signal handler failure must not interfere with
    Celery's own failure-handling path.

    NOTE: task kwargs are intentionally NOT stored — they may contain
    API keys, OAuth tokens, or other secrets. Only the task name,
    exception type/message, and a truncated traceback are recorded.
    """
    try:
        from apps.core.models import ErrorEvent

        name = getattr(sender, "name", str(sender)) if sender is not None else "unknown"
        tb = ""
        if einfo is not None:
            tb = str(einfo)[:4000]  # truncate; do NOT include task kwargs
        ErrorEvent.record(
            level="error",
            source=f"celery.task:{name}",
            message=(
                f"{type(exception).__name__}: {exception}"[:1000]
                if exception is not None
                else "task failed"
            ),
            detail={"task_id": str(task_id), "traceback": tb},
            fingerprint=name or "",
        )
    except Exception:
        logger.warning("error_event.capture_failed", exc_info=True)
