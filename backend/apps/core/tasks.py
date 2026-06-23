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
    * RegimeReading  — keep AI_RETENTION_REGIME_DAYS       (default 180d)
    * DeskEntry      — keep AI_RETENTION_DESK_DAYS         (default 180d)
    * BookSnapshot   — keep AI_RETENTION_BOOK_DAYS         (default 365d)
      (the three above are append-only leaves with no inbound FK; the latest row of
      each is always recent, so old rows are pure history that grows every pg_dump.)

    Models NEVER touched
    --------------------
    Snapshot, SnapshotSection, SnapshotImage, Message, AIRun,
    Thesis, PostMortem, DecisionJournalEntry, Backup* — all load-bearing.
    WarRoomRun / CoverageRevision / EvalRun / TriggerFiring — kept as audit/cost trails.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.book.models import BookSnapshot
    from apps.core.models import ErrorEvent
    from apps.core.runtime_config import runtime_config
    from apps.market.models import OHLCBar, OptionChainSnapshot
    from apps.observer.models import Notification
    from apps.strategy.models import DeskEntry, RegimeReading

    rc = runtime_config()
    results: dict[str, int] = {}

    def _prune(label: str, qs_factory, days: int) -> None:
        if not days or days < 1:
            # A non-positive window sets cutoff >= now and would delete EVERY row.
            # Treat <1 as "pruning disabled" for this model — a guard against an
            # env/DB misconfig (e.g. retention_*_days=0) wiping load-bearing data.
            results[label] = 0
            log.info("core.prune_retention.%s skipped (retention<1 day)", label)
            return
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
        rc.retention_ohlc_days,
    )
    _prune(
        "chain",
        lambda c: OptionChainSnapshot.objects.filter(fetched_at__lt=c),
        rc.retention_chain_days,
    )
    _prune(
        "notifications",
        lambda c: Notification.objects.filter(created_at__lt=c),
        rc.retention_notification_days,
    )
    _prune(
        "errors",
        lambda c: ErrorEvent.objects.filter(created_at__lt=c, resolved=True),
        rc.retention_error_days,
    )
    _prune(
        "regime",
        lambda c: RegimeReading.objects.filter(created_at__lt=c),
        rc.retention_regime_days,
    )
    _prune(
        "desk",
        lambda c: DeskEntry.objects.filter(created_at__lt=c),
        rc.retention_desk_days,
    )
    _prune(
        "book",
        lambda c: BookSnapshot.objects.filter(created_at__lt=c),
        rc.retention_book_days,
    )

    return results
