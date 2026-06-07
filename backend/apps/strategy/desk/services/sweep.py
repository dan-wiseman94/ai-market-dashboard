"""Orchestrate one sweep: detect -> rank -> cooldown -> top-K -> investigate ->
persist DeskEntry + notify. Never raises out of the loop."""

from __future__ import annotations

import logging

from apps.strategy.desk import constants as C
from apps.strategy.desk.services.detectors import run_detectors
from apps.strategy.desk.services.investigate import investigate
from apps.strategy.desk.services.scoring import in_cooldown, originated_today, rank
from apps.strategy.desk.services.universe import build_universe
from apps.strategy.models import DeskEntry

log = logging.getLogger(__name__)


def _notify(entry: DeskEntry) -> None:
    from apps.observer.services.notifications import notify

    notify(
        user_id=None,
        kind="desk",
        title=f"Desk: {entry.anomaly_type} {entry.ticker or 'book'}",
        body=entry.finding[:200],
        link="/desk",
        meta={"entry_id": entry.id},
    )


def run_sweep(top_k: int = C.TOP_K) -> int:
    universe = build_universe()
    candidates = rank(run_detectors(universe))
    already_today = originated_today()
    created = 0
    dropped = 0
    capped = 0
    for cand in candidates:
        if already_today + created >= C.DAILY_ORIGINATION_CAP:
            capped += 1
            continue
        if created >= top_k:
            dropped += 1
            continue
        if in_cooldown(cand["anomaly_type"], cand.get("ticker", "")):
            continue
        result = investigate(cand)
        if result is None:
            continue
        entry = DeskEntry.objects.create(
            anomaly_type=cand["anomaly_type"],
            ticker=cand.get("ticker", "") or "",
            severity=cand.get("severity", 0.0),
            evidence=cand.get("evidence", {}),
            finding=result["finding"],
            suggested_actions=result["suggested_actions"],
            investigation_thread_id=result.get("investigation_thread_id"),
        )
        try:
            _notify(entry)
        except Exception:
            log.warning("desk.notify_failed", exc_info=True)
        created += 1
    if dropped:
        log.info(
            "desk.sweep dropped %d candidates beyond top_k=%d (no silent truncation)",
            dropped,
            top_k,
        )
    if capped:
        log.info(
            "desk.sweep dropped %d candidates at daily origination cap=%d (%d already today)",
            capped,
            C.DAILY_ORIGINATION_CAP,
            already_today,
        )
    return created
