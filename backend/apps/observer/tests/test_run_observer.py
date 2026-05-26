from unittest.mock import patch

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import run_observer
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads.models import Thread


def _profile():
    return TradingProfile.objects.create(name="P", style="x")


@pytest.mark.django_db
def test_run_observer_skips_when_disabled():
    s = ObserverSchedule.objects.create(name="x", profile=_profile(), enabled=False)
    assert run_observer(s.id) is None
    assert Snapshot.objects.count() == 0


@pytest.mark.django_db
def test_run_observer_skips_when_market_closed():
    s = ObserverSchedule.objects.create(
        name="x",
        profile=_profile(),
        market_hours_only=True,
    )
    with patch("apps.observer.services.run.any_market_open", return_value=False):
        assert run_observer(s.id) is None
    assert Snapshot.objects.count() == 0


@pytest.mark.django_db
def test_run_observer_writes_placeholder_when_cost_capped():
    p = _profile()
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
def test_run_observer_happy_path_creates_snapshot_message_and_notification():
    p = _profile()
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
