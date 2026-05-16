"""Rung 3 — snapshots in ready / partial-via-failed-sections / failed states.

Snapshot.status only supports ``pending|ready|failed`` — there is no "partial"
status. We represent the partial case as a ``ready`` Snapshot with one
``failed`` SnapshotSection so downstream UI/observability code still observes
"some sections ok, news failed".

Idempotent.
"""

from __future__ import annotations

SECTION_KINDS = ("quotes", "ohlc", "chain", "positions", "breadth", "news", "image")


def seed_snapshots() -> None:
    from e2e.fixtures.seed_market import seed_market

    seed_market()

    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot, SnapshotSection

    profile = TradingProfile.objects.get(name="E2E Default")

    # Three fully-ready snapshots — every section ``done`` with payload_tokens stamped.
    for idx in range(3):
        snap, _ = Snapshot.objects.update_or_create(
            profile=profile,
            objective=f"e2e ready snap {idx}",
            defaults={"status": "ready", "source": "manual"},
        )
        for kind in SECTION_KINDS:
            SnapshotSection.objects.update_or_create(
                snapshot=snap,
                kind=kind,
                defaults={
                    "status": "done",
                    "payload": {"mock": kind},
                    "payload_tokens": 128,
                },
            )

    # Partial — Snapshot.status="ready" with one failed section (news).
    partial, _ = Snapshot.objects.update_or_create(
        profile=profile,
        objective="e2e partial snap",
        defaults={"status": "ready", "source": "manual"},
    )
    for kind in SECTION_KINDS:
        SnapshotSection.objects.update_or_create(
            snapshot=partial,
            kind=kind,
            defaults={
                "status": "failed" if kind == "news" else "done",
                "payload": {} if kind == "news" else {"mock": kind},
                "payload_tokens": 0 if kind == "news" else 128,
                "error": "mock_503" if kind == "news" else "",
            },
        )

    # Fully failed — no sections populated.
    Snapshot.objects.update_or_create(
        profile=profile,
        objective="e2e failed snap",
        defaults={"status": "failed", "source": "manual"},
    )
