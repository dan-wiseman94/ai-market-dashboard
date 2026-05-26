"""Rung 8 — theses + post-mortems + a decision-journal entry.

Builds on the threads rung so a thesis can reference a real source thread and
(when present) a ready snapshot. Lays down:

  * "E2E open thesis"   — AAPL bullish, conviction 4, status=open, with the
    7/30/90-day post-mortems scheduled (so the detail page renders pm cards).
  * "E2E closed thesis" — TSLA bearish, conviction 2, status=closed_win.
  * One DecisionJournalEntry ("acted") on the source thread.

Idempotent.
"""

from __future__ import annotations


def seed_thesis() -> None:
    from e2e.fixtures.seed_threads import seed_threads

    seed_threads()

    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot
    from apps.thesis.models import DecisionJournalEntry, Thesis
    from apps.thesis.services.postmortem import schedule_postmortems
    from apps.threads.models import Thread

    profile = TradingProfile.objects.filter(name="E2E Default").first()
    thread = Thread.objects.order_by("id").first()
    snapshot = Snapshot.objects.filter(status="ready").order_by("id").first()

    open_thesis, _ = Thesis.objects.update_or_create(
        title="E2E open thesis",
        defaults={
            "ticker": "AAPL",
            "direction": "bullish",
            "rationale": "Seeded open thesis for E2E coverage.",
            "conviction": 4,
            "horizon_days": 30,
            "status": "open",
            "profile": profile,
            "thread": thread,
            "snapshot": snapshot,
        },
    )
    schedule_postmortems(open_thesis)  # idempotent — 7/30/90-day PMs

    Thesis.objects.update_or_create(
        title="E2E closed thesis",
        defaults={
            "ticker": "TSLA",
            "direction": "bearish",
            "rationale": "Seeded closed thesis for E2E coverage.",
            "conviction": 2,
            "horizon_days": 30,
            "status": "closed_win",
            "close_note": "Played out as expected.",
            "profile": profile,
        },
    )

    if thread is not None and not DecisionJournalEntry.objects.filter(thread=thread).exists():
        DecisionJournalEntry.objects.create(
            thread=thread,
            thesis=open_thesis,
            decision="acted",
            note="Seeded journal entry for E2E coverage.",
        )
