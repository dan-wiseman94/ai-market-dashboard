"""Backfill helper shared by the data migration and its test (migration-safe:
takes model classes, no direct imports of the live models)."""

from __future__ import annotations


def _first_quotes_key(sections):
    for sec in sections:
        if sec.kind == "quotes" and isinstance(sec.payload, dict) and sec.payload:
            return str(next(iter(sec.payload))).upper()
    return None


def populate(Snapshot, SnapshotSection):
    for snap in Snapshot.objects.all().iterator():
        ticker = _first_quotes_key(snap.sections.all())
        if ticker and snap.primary_ticker != ticker:
            snap.primary_ticker = ticker
            snap.save(update_fields=["primary_ticker"])
