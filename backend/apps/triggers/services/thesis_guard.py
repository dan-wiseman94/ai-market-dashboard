"""Translate a thesis target/invalidation into a managed price-guard trigger."""

from __future__ import annotations

import logging

from apps.profiles.models import TradingProfile
from apps.triggers.models import EventTrigger

log = logging.getLogger(__name__)


def build_guard_condition(thesis) -> dict | None:
    t, inv, d = thesis.target_price, thesis.invalidation_price, thesis.direction
    leaves = []
    if d == "bearish":
        if t is not None:
            leaves.append(_leaf(thesis.ticker, "crosses_below", float(t)))
        if inv is not None:
            leaves.append(_leaf(thesis.ticker, "crosses_above", float(inv)))
    else:  # bullish / neutral: target above, invalidation below
        if t is not None:
            leaves.append(_leaf(thesis.ticker, "crosses_above", float(t)))
        if inv is not None:
            leaves.append(_leaf(thesis.ticker, "crosses_below", float(inv)))
    return {"any": leaves} if leaves else None


def _leaf(ticker: str, op: str, value: float) -> dict:
    return {"metric": "price", "ticker": ticker.upper(), "op": op, "value": value}


def sync_thesis_guard(thesis) -> EventTrigger | None:
    """Idempotent: create/update the guard when enabled+open+priced; else disable it."""
    existing = EventTrigger.objects.filter(source_thesis=thesis).first()
    condition = build_guard_condition(thesis)
    active = thesis.guard_enabled and thesis.status == "open" and condition is not None
    if not active:
        if existing and existing.enabled:
            existing.enabled = False
            existing.save(update_fields=["enabled"])
        return existing
    profile = thesis.profile or TradingProfile.objects.first()
    if profile is None:
        log.warning("thesis_guard: no profile available for thesis %s", thesis.id)
        return None
    if existing:
        existing.condition = condition
        existing.profile = profile
        existing.enabled = True
        existing.save(update_fields=["condition", "profile", "enabled"])
        return existing
    return EventTrigger.objects.create(
        name=f"Guard: {thesis.title}"[:100],
        profile=profile,
        condition=condition,
        cooldown_seconds=21600,
        enabled=True,
        source_thesis=thesis,
    )
