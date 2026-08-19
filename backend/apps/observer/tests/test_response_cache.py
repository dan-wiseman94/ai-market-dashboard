"""Observer response cache: a fire whose assembled prompt is byte-identical
to a recent prior fire reuses that observation instead of calling the AI again."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import fire_observer
from apps.snapshots.models import Snapshot
from apps.threads.models import Message, Thread


def _fire(schedule, snap):
    """Fire fire_observer with capture/serialize/cost mocked so the assembled
    prompt is deterministic; return the patched run_ai_on_message mock."""
    with ExitStack() as stack:
        for cm in (
            patch("apps.observer.services.run.any_market_open", return_value=True),
            patch("apps.observer.services.run.check_daily_cap"),
            patch("apps.observer.services.run.check_monthly_cap"),
            patch("apps.observer.services.run.capture", return_value=snap),
            patch("apps.observer.services.run.serialize_for_ai", return_value="## BODY"),
            patch("apps.observer.services.run.notify"),
        ):
            stack.enter_context(cm)
        run_ai = stack.enter_context(patch("apps.observer.services.run.run_ai_on_message"))
        fire_observer(schedule.id)
        return run_ai


@pytest.mark.django_db
@override_settings(OBSERVER_RESPONSE_CACHE_ENABLED=True)
def test_reuses_cached_response_for_identical_prompt(profile):
    p = profile
    s = ObserverSchedule.objects.create(
        name="x", profile=p, market_hours_only=False, default_includes=["quotes"]
    )
    snap = Snapshot.objects.create(
        profile=p, includes=["quotes"], source="observer", status="ready"
    )

    # Fire 1: nothing cached -> the AI is dispatched, and the user turn records a hash.
    run_ai1 = _fire(s, snap)
    run_ai1.delay.assert_called_once()
    thread = Thread.objects.get(profile=p, kind="observer")
    user1 = thread.messages.filter(role="user").order_by("created_at").first()
    assert user1.content.get("prompt_hash")

    # Simulate fire 1's completed AI response landing on the thread.
    Message.objects.create(
        thread=thread, role="assistant", content={"text": "PRIOR OBSERVATION"}, status="done"
    )

    # Fire 2: byte-identical prompt -> cache HIT -> no AI call, reuse the text.
    run_ai2 = _fire(s, snap)
    run_ai2.delay.assert_not_called()
    cached = thread.messages.filter(role="assistant", content__kind="cached_observation").first()
    assert cached is not None
    assert cached.content["text"] == "PRIOR OBSERVATION"


@pytest.mark.django_db
def test_cache_off_by_default_always_dispatches(profile):
    p = profile
    s = ObserverSchedule.objects.create(
        name="x", profile=p, market_hours_only=False, default_includes=["quotes"]
    )
    snap = Snapshot.objects.create(
        profile=p, includes=["quotes"], source="observer", status="ready"
    )

    _fire(s, snap).delay.assert_called_once()
    thread = Thread.objects.get(profile=p, kind="observer")
    Message.objects.create(
        thread=thread, role="assistant", content={"text": "PRIOR"}, status="done"
    )
    # Cache disabled (default) -> the second identical fire still dispatches the AI.
    _fire(s, snap).delay.assert_called_once()
