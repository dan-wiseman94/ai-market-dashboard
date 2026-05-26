"""Per-thesis review-thread lookup helper.

Mirrors apps.observer.services.threads.get_or_create_observer_thread, but keyed
via the Thesis.review_thread FK (one review thread per thesis) rather than a
get_or_create on Thread fields.
"""

from __future__ import annotations

from apps.threads.models import Thread

from ..models import Thesis


def get_or_create_review_thread(thesis: Thesis) -> Thread:
    """Return the per-thesis review thread, creating it on first call.

    Uses kind="consult" — post-mortems are one-shot reviews, not an ongoing
    chat or observer timeline; we deliberately do NOT add a new Thread kind.
    """
    if thesis.review_thread_id:
        return thesis.review_thread

    thread = Thread.objects.create(
        profile=thesis.profile,
        kind="consult",
        title=f"Post-mortem: {thesis.title}",
    )
    thesis.review_thread = thread
    thesis.save(update_fields=["review_thread"])
    return thread
