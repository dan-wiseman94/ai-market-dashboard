from unittest.mock import patch

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import run_observer
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread


@pytest.mark.django_db
def test_run_observer_skips_when_disabled(profile):
    s = ObserverSchedule.objects.create(name="x", profile=profile, enabled=False)
    assert run_observer(s.id) is None
    assert Snapshot.objects.count() == 0


@pytest.mark.django_db
def test_run_observer_skips_when_market_closed(profile):
    s = ObserverSchedule.objects.create(
        name="x",
        profile=profile,
        market_hours_only=True,
    )
    with patch("apps.observer.services.run.any_market_open", return_value=False):
        assert run_observer(s.id) is None
    assert Snapshot.objects.count() == 0


@pytest.mark.django_db
def test_run_observer_writes_placeholder_when_cost_capped(profile):
    p = profile
    s = ObserverSchedule.objects.create(
        name="x",
        profile=p,
        market_hours_only=False,
    )
    from apps.ai.cost import CostCapExceededError

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch(
            "apps.observer.services.run.check_daily_cap", side_effect=CostCapExceededError("cap")
        ),
    ):
        assert run_observer(s.id) is None
    thread = Thread.objects.get(profile=p, kind="observer")
    placeholder = thread.messages.first()
    assert placeholder is not None
    assert placeholder.role == "system"
    assert "skipped" in placeholder.content["text"].lower()
    assert "cost cap" in placeholder.content["text"].lower()
    assert Snapshot.objects.count() == 0
    s.refresh_from_db()
    assert s.last_fired_at is not None


@pytest.mark.django_db
def test_run_observer_happy_path_creates_snapshot_message_and_notification(profile):
    p = profile
    s = ObserverSchedule.objects.create(
        name="hourly",
        profile=p,
        market_hours_only=False,
        objective_template="What changed?",
        default_includes=["quotes"],
        default_watchlist_tickers=["SPY"],
    )
    fake_snap = Snapshot.objects.create(
        profile=p,
        objective="What changed?",
        includes=["quotes"],
        source="observer",
        status="pending",
    )
    fake_serialize = "## SNAPSHOT BODY"

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.check_daily_cap"),
        patch("apps.observer.services.run.capture", return_value=fake_snap) as cap,
        patch("apps.observer.services.run.serialize_for_ai", return_value=fake_serialize),
        patch("apps.observer.services.run.run_ai_on_message") as run_ai,
        patch("apps.observer.services.run.notify") as notif,
    ):
        result = run_observer(s.id)

    assert result == fake_snap.id
    cap.assert_called_once()
    cap_kwargs = cap.call_args.kwargs
    assert cap_kwargs["profile"] == p
    assert cap_kwargs["objective"] == "What changed?"
    assert cap_kwargs["includes"] == ["quotes"]
    assert cap_kwargs["source"] == "observer"
    assert cap_kwargs["watchlist_tickers"] == ["SPY"]

    thread = Thread.objects.get(profile=p, kind="observer")
    msg = thread.messages.get()
    assert msg.role == "user"
    assert msg.content["text"] == fake_serialize
    assert msg.snapshot_ref == fake_snap

    run_ai.delay.assert_called_once()
    delay_kwargs = run_ai.delay.call_args.kwargs
    assert delay_kwargs["thread_id"] == thread.id
    assert delay_kwargs["user_message_id"] == msg.id

    notif.assert_called_once()
    notif_kwargs = notif.call_args.kwargs
    assert notif_kwargs["kind"] == "observer_done"
    assert notif_kwargs["link"] == f"/threads/observer/{p.id}"

    s.refresh_from_db()
    assert s.last_fired_at is not None


@pytest.mark.django_db
def test_run_observer_batch_submit_failure_writes_failed_message(profile):
    """A failed batch submit must surface in the observer thread — the timeline
    reads Messages, so a log-only failure is invisible in the UI."""
    p = profile
    s = ObserverSchedule.objects.create(
        name="overnight",
        profile=p,
        market_hours_only=False,
        use_batch=True,
        default_watchlist_tickers=["SPY"],
    )
    fake_snap = Snapshot.objects.create(profile=p, source="observer", status="ready")

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.capture", return_value=fake_snap),
        patch(
            "apps.observer.services.batch.submit_watchlist_batch",
            side_effect=ValueError("no claude key"),
        ) as submit,
    ):
        result = run_observer(s.id)

    assert result == fake_snap.id
    # The submit is grounded in the snapshot the fire just captured.
    submit.assert_called_once_with(s.id, snapshot_id=fake_snap.id)
    thread = Thread.objects.get(profile=p, kind="observer")
    msg = thread.messages.get()
    assert msg.role == "assistant"
    assert msg.status == "failed"
    assert "batch submit failed" in msg.content["text"]
    assert "no claude key" in msg.error


@pytest.mark.django_db
def test_run_observer_coverage_hook_failure_is_logged_not_fatal(caplog, profile):
    """A broken coverage auto-revise hook must not fail the fire, and must leave
    a warning in the logs — a silent suppress would hide the breakage forever."""
    p = profile
    s = ObserverSchedule.objects.create(
        name="hourly",
        profile=p,
        market_hours_only=False,
        default_watchlist_tickers=["SPY"],
    )
    fake_snap = Snapshot.objects.create(profile=p, source="observer", status="ready")

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.check_daily_cap"),
        patch("apps.observer.services.run.capture", return_value=fake_snap),
        patch("apps.observer.services.run.serialize_for_ai", return_value="## SNAPSHOT BODY"),
        patch("apps.observer.services.run.run_ai_on_message"),
        patch("apps.observer.services.run.notify") as notif,
        patch(
            "apps.observer.services.run.maybe_revise_from_snapshot",
            side_effect=RuntimeError("db down"),
        ),
        caplog.at_level("WARNING"),
    ):
        result = run_observer(s.id)

    assert result == fake_snap.id
    notif.assert_called_once()
    s.refresh_from_db()
    assert s.last_fired_at is not None
    hook_warnings = [r for r in caplog.records if "coverage auto-revise hook failed" in r.message]
    assert hook_warnings, "expected a warning about the failed coverage hook"
    assert hook_warnings[0].exc_info is not None
