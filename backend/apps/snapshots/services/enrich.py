"""Derived 'intel' snapshot enrichment: sector rotation + relative strength + IV summary.

Runs post-capture (after primary_ticker is known). Additive and best-effort: a
failure here costs the intel section, never the capture.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from apps.market.services.intel import iv_summary, relative_strength, sector_rotation
from apps.snapshots.models import SnapshotSection

log = logging.getLogger(__name__)


def _safe(fn):
    try:
        return fn()
    except Exception:
        log.warning("intel.section_failed", exc_info=True)
        return None


def build_intel_payload(snap) -> dict:
    """Gated, best-effort. Returns {} when nothing applies or computes."""
    payload: dict = {}
    if "breadth" in snap.includes:
        payload["rotation"] = _safe(sector_rotation)
    if snap.primary_ticker:
        payload["relative_strength"] = _safe(lambda: relative_strength(snap.primary_ticker))
    if "chain" in snap.includes and snap.primary_ticker:
        payload["iv"] = _safe(lambda: iv_summary(snap.primary_ticker, at=timezone.now()))
    return {k: v for k, v in payload.items() if v}


def enrich_snapshot(snap) -> None:
    """Write a SnapshotSection(kind='intel') from build_intel_payload. NEVER raises."""
    try:
        payload = build_intel_payload(snap)
        if not payload:
            return
        from apps.snapshots.services import stamp_payload_tokens

        section, _ = SnapshotSection.objects.update_or_create(
            snapshot=snap,
            kind="intel",
            defaults={"payload": payload, "status": "done", "error": ""},
        )
        stamp_payload_tokens(section)
    except Exception:
        log.warning("intel.enrich_failed", exc_info=True)
