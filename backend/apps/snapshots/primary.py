"""Primary-ticker derivation + prior-snapshot selection for a snapshot."""

from __future__ import annotations

from typing import Any

from apps.snapshots.models import Snapshot


def primary_ticker_from_quotes(quotes_payload: Any) -> str | None:
    """First ticker key in a quotes-section payload, upper-cased; None if absent."""
    if not isinstance(quotes_payload, dict) or not quotes_payload:
        return None
    return str(next(iter(quotes_payload))).upper()


def primary_ticker(snapshot: Snapshot) -> str | None:
    """Derive the primary ticker from a snapshot's quotes section.

    Iterates ``sections.all()`` (prefetch-friendly — no extra query when the
    caller has prefetched) rather than a filtered query.
    """
    for sec in snapshot.sections.all():
        if sec.kind == "quotes" and isinstance(sec.payload, dict) and sec.payload:
            return primary_ticker_from_quotes(sec.payload)
    return None


def previous_snapshot_for(snap: Snapshot) -> Snapshot | None:
    """Most-recent prior READY snapshot sharing snap.primary_ticker."""
    if not snap.primary_ticker:
        return None
    return (
        Snapshot.objects.filter(
            primary_ticker=snap.primary_ticker,
            status="ready",
            captured_at__lt=snap.captured_at,
        )
        .exclude(id=snap.id)
        .order_by("-captured_at")
        .first()
    )
