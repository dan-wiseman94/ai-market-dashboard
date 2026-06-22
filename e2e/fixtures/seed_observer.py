"""Rung 5 — observer schedules + observer thread with mixed outcomes.

Four schedules:
  * E2E active schedule — enabled, mode=full
  * E2E paused schedule — disabled, mode=full
  * E2E structured schedule — enabled, mode=full, structured=True
  * E2E diff schedule — enabled, mode=diff

One observer Thread with 4 messages: 2 done, 1 failed, 1 cost-cap system note.

Idempotent.
"""

from __future__ import annotations


def seed_observer() -> None:
    from e2e.fixtures.seed_threads import seed_threads

    seed_threads()

    from apps.observer.models import ObserverSchedule
    from apps.observer.services.sync import sync_periodic_task
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Message, Thread

    profile = TradingProfile.objects.get(name="E2E Default")

    s1, _ = ObserverSchedule.objects.update_or_create(
        name="E2E active schedule",
        defaults={"profile": profile, "enabled": True, "mode": "full"},
    )
    sync_periodic_task(s1, cron="*/5 * * * *")
    s2, _ = ObserverSchedule.objects.update_or_create(
        name="E2E paused schedule",
        defaults={"profile": profile, "enabled": False, "mode": "full"},
    )
    sync_periodic_task(s2, cron="*/5 * * * *")
    s3, _ = ObserverSchedule.objects.update_or_create(
        name="E2E structured schedule",
        defaults={
            "profile": profile,
            "enabled": True,
            "mode": "full",
            "structured": True,
        },
    )
    sync_periodic_task(s3, cron="*/5 * * * *")
    s4, _ = ObserverSchedule.objects.update_or_create(
        name="E2E diff schedule",
        defaults={"profile": profile, "enabled": True, "mode": "diff"},
    )
    sync_periodic_task(s4, cron="*/5 * * * *")

    obs_thread, _ = Thread.objects.get_or_create(
        title="E2E observer thread",
        defaults={"profile": profile, "schedule": s1, "kind": "observer"},
    )
    if not obs_thread.messages.exists():
        for i in range(2):
            Message.objects.create(
                thread=obs_thread,
                role="assistant",
                status="done",
                content={"text": f"observation {i}"},
            )
        Message.objects.create(
            thread=obs_thread,
            role="assistant",
            status="failed",
            content={"text": "mock failure"},
            error="mock_failure",
        )
        Message.objects.create(
            thread=obs_thread,
            role="system",
            status="done",
            content={"text": "skipped: cost cap exceeded"},
        )

    # The observer timeline page (/threads/observer/<pid>) resolves the canonical
    # per-profile thread via get_or_create_observer_thread (schedule__isnull=True,
    # title "Observer: <name>") — NOT the schedule-linked thread above. Seed a
    # cost-cap skip message there so the timeline actually surfaces one. The "⏸"
    # prefix matches ObserverTimelinePage's isSkipped styling so it renders in the
    # collapsed headline rather than only on expand.
    from apps.observer.services.threads import get_or_create_observer_thread

    canonical = get_or_create_observer_thread(profile)
    if not canonical.messages.filter(role="system", content__text__icontains="cost cap").exists():
        Message.objects.create(
            thread=canonical,
            role="system",
            status="done",
            content={"text": "⏸ Observer fire skipped: cost cap exceeded"},
        )
