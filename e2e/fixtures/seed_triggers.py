"""Rung 6 — event triggers + firings.

Three triggers:
  * E2E always fires — simple leaf condition.
  * E2E pct_change — windowed leaf condition.
  * E2E complex DSL — nested all/any/not.

The first trigger gets 5 firings across day 0 for downstream analytics.

Idempotent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def seed_triggers() -> None:
    from e2e.fixtures.seed_observer import seed_observer

    seed_observer()

    from apps.observer.models import EventTrigger, TriggerFiring
    from apps.profiles.models import TradingProfile

    profile = TradingProfile.objects.get(name="E2E Default")

    simple, _ = EventTrigger.objects.update_or_create(
        profile=profile,
        name="E2E always fires",
        defaults={
            "condition": {
                "ticker": "AAPL",
                "metric": "price",
                "op": ">",
                "value": 0,
            },
            "enabled": True,
            "cooldown_seconds": 60,
        },
    )
    EventTrigger.objects.update_or_create(
        profile=profile,
        name="E2E pct_change",
        defaults={
            "condition": {
                "ticker": "AAPL",
                "metric": "pct_change",
                "op": ">",
                "value": 5,
                "window": "1h",
            },
            "enabled": True,
            "cooldown_seconds": 60,
        },
    )
    EventTrigger.objects.update_or_create(
        profile=profile,
        name="E2E complex DSL",
        defaults={
            "condition": {
                "all": [
                    {"ticker": "AAPL", "metric": "price", "op": ">", "value": 170},
                    {
                        "any": [
                            {
                                "ticker": "MSFT",
                                "metric": "pct_change",
                                "op": ">",
                                "value": 1,
                                "window": "1h",
                            },
                            {
                                "not": {
                                    "ticker": "VIX",
                                    "metric": "price",
                                    "op": ">",
                                    "value": 20,
                                }
                            },
                        ]
                    },
                ]
            },
            "enabled": True,
            "cooldown_seconds": 60,
        },
    )

    # Five firings on day 0; reset prior E2E firings for idempotency.
    TriggerFiring.objects.filter(trigger=simple).delete()
    now = datetime.now(UTC)
    for i in range(5):
        firing = TriggerFiring.objects.create(trigger=simple, matched_values={"price": 175.0 + i})
        TriggerFiring.objects.filter(pk=firing.pk).update(fired_at=now - timedelta(minutes=i * 15))
