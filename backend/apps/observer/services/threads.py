"""Observer-thread lookup helper (Q4: one observer thread per profile)."""

from __future__ import annotations

from apps.profiles.models import TradingProfile
from apps.threads.models import Thread


def get_or_create_observer_thread(profile: TradingProfile) -> Thread:
    """Return the per-profile observer thread, creating it on first call."""
    obj, _ = Thread.objects.get_or_create(
        profile=profile,
        kind="observer",
        schedule__isnull=True,
        defaults={"title": f"Observer: {profile.name}"},
    )
    return obj
