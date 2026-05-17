"""Rung 7 — AI runs across providers + heatmap firings.

20 ``AIRun`` rows spread across 7 days x 3 providers with varied cost +
latency. Each run is attached to a freshly-created assistant ``Message`` on a
ready snapshot, so the leaderboard's forward-return correlation has both a
snapshot and (via the seeded OHLC bars) price history to work with.

15 extra ``TriggerFiring`` rows fill the trigger heatmap grid.

Idempotent.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal


def seed_analytics() -> None:
    from e2e.fixtures.seed_triggers import seed_triggers

    seed_triggers()

    from apps.snapshots.models import Snapshot
    from apps.threads.models import AIRun, Message, Thread
    from apps.triggers.models import EventTrigger, TriggerFiring

    rng = random.Random(7)
    now = datetime.now(UTC)
    providers = ("claude", "openai", "local")
    models = {
        "claude": "claude-sonnet-4-6",
        "openai": "gpt-5-mini",
        "local": "local-7b",
    }

    ready_snaps = list(Snapshot.objects.filter(status="ready"))
    thread = Thread.objects.filter(title="E2E plain thread").first()
    if thread is None:
        return

    # Reset previously seeded AIRuns so the rung stays deterministic.
    AIRun.objects.filter(message__thread=thread).delete()

    for i in range(20):
        prov = providers[i % 3]
        snap = ready_snaps[i % max(len(ready_snaps), 1)] if ready_snaps else None
        msg = Message.objects.create(
            thread=thread,
            role="assistant",
            status="done",
            content={"text": f"analytics seed {i}"},
            snapshot_ref=snap,
        )
        AIRun.objects.create(
            message=msg,
            provider=prov,
            model=models[prov],
            input_tokens=rng.randint(500, 8_000),
            output_tokens=rng.randint(100, 2_000),
            cached_tokens=0,
            cost_usd=Decimal(str(round(rng.uniform(0.001, 0.25), 6))),
            latency_ms=rng.randint(300, 15_000),
            status="done",
        )
        # Spread the created_at backwards
        AIRun.objects.filter(message=msg).update(
            created_at=now - timedelta(days=i % 7, hours=rng.randint(0, 23))
        )

    # 15 extra firings for the heatmap.
    trig = EventTrigger.objects.filter(name="E2E always fires").first()
    if trig is not None:
        for i in range(15):
            firing = TriggerFiring.objects.create(trigger=trig, matched_values={"price": 175.0})
            TriggerFiring.objects.filter(pk=firing.pk).update(
                fired_at=now - timedelta(days=i % 7, hours=i)
            )
