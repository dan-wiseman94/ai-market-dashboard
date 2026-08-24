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


def last_price(snapshot, ticker: str | None = None) -> float | None:
    """Last price for ``ticker`` (default: the snapshot's primary ticker) from the
    snapshot's own quotes section — no fetch, best-effort.

    Only ``status=="done"`` sections count ("done" is the section terminal state; a
    failed/pending quotes section carries no trustworthy payload). Iterates
    ``sections.all()`` (prefetch-friendly — no extra query when the caller has
    prefetched). Returns None on a missing snapshot/ticker/section or when the
    value won't coerce to float.
    """
    if snapshot is None:
        return None
    key = ticker or getattr(snapshot, "primary_ticker", None)
    if not key:
        return None
    for sec in snapshot.sections.all():
        if sec.kind != "quotes" or sec.status != "done" or not isinstance(sec.payload, dict):
            continue
        row = sec.payload.get(key)
        if not isinstance(row, dict):
            continue
        try:
            return float(row["last"])
        except (KeyError, TypeError, ValueError):
            return None
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
