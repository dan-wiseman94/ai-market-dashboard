"""Core Celery tasks: smoke-test ping + retention pruning."""

from __future__ import annotations

import logging

from celery import shared_task

log = logging.getLogger(__name__)


@shared_task(name="core.ping")
def ping(name: str | None = None) -> str:
    """Return 'pong' or 'pong <name>'. Used to verify Celery end-to-end."""
    return "pong" if name is None else f"pong {name}"


@shared_task(name="core.prune_retention")
def prune_retention() -> dict:
    """Age-prune unreferenced time-series + ephemera with generous windows.

    FK-SAFE: only deletes standalone models that are never pointed at by
    load-bearing FKs that would orphan needed data.

    Never raises — a failure on one model is logged and the rest still run
    (mirrors the per-section defensive style from the capture pipeline).
    Idempotent: re-running after the cutoff has passed deletes nothing new.
    Configurable via AI_RETENTION_* settings (env-overridable).

    Models pruned
    -------------
    * OHLCBar        — keep AI_RETENTION_OHLC_DAYS         (default 400d)
    * OptionChainSnapshot — keep AI_RETENTION_CHAIN_DAYS   (default 120d)
    * Notification   — keep AI_RETENTION_NOTIFICATION_DAYS (default 90d)
    * ErrorEvent     — keep AI_RETENTION_ERROR_DAYS        (default 90d),
                       resolved=True only (unresolved kept regardless of age)

    Models NEVER touched
    --------------------
    Snapshot, SnapshotSection, SnapshotImage, Message, AIRun,
    Thesis, PostMortem, DecisionJournalEntry, Backup* — all load-bearing.
    """
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from apps.core.models import ErrorEvent
    from apps.market.models import OHLCBar, OptionChainSnapshot
    from apps.observer.models import Notification

    results: dict[str, int] = {}

    def _prune(label: str, qs_factory, days: int) -> None:
        try:
            cutoff = timezone.now() - timedelta(days=days)
            n, _ = qs_factory(cutoff).delete()
            results[label] = n
            log.info("core.prune_retention.%s deleted=%d cutoff=%s", label, n, cutoff.date())
        except Exception as exc:
            log.warning("core.prune_retention.%s failed: %s", label, exc)
            results[label] = -1

    _prune(
        "ohlc",
        lambda c: OHLCBar.objects.filter(ts__lt=c),
        settings.AI_RETENTION_OHLC_DAYS,
    )
    _prune(
        "chain",
        lambda c: OptionChainSnapshot.objects.filter(fetched_at__lt=c),
        settings.AI_RETENTION_CHAIN_DAYS,
    )
    _prune(
        "notifications",
        lambda c: Notification.objects.filter(created_at__lt=c),
        settings.AI_RETENTION_NOTIFICATION_DAYS,
    )
    _prune(
        "errors",
        lambda c: ErrorEvent.objects.filter(created_at__lt=c, resolved=True),
        settings.AI_RETENTION_ERROR_DAYS,
    )

    return results
