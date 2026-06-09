"""Observer-thread lookup helper (Q4: one observer thread per profile)."""

from __future__ import annotations

from apps.profiles.models import TradingProfile
from apps.threads.models import Thread


def get_or_create_observer_thread(profile: TradingProfile) -> Thread:
    """Return the per-profile observer thread, creating it on first call.

    Resolve by oldest-match rather than ``get_or_create``: the latter is not atomic
    (there is no unique constraint on profile+kind+schedule-null), so two observer fires
    racing to create the canonical thread — e.g. a beat-fired ``run_observer`` and another
    caller — could leave two rows, after which ``get_or_create``'s implicit ``get`` would
    raise ``MultipleObjectsReturned`` and 500 every later fire / timeline load. ``.first()``
    always returns the same (oldest) row, tolerating a rare duplicate instead of crashing.
    """
    existing = (
        Thread.objects.filter(profile=profile, kind="observer", schedule__isnull=True)
        .order_by("id")
        .first()
    )
    if existing is not None:
        return existing
    return Thread.objects.create(
        profile=profile, kind="observer", schedule=None, title=f"Observer: {profile.name}"
    )
