from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import run_observer
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.thesis.models import Thesis
from apps.threads.models import Message, Thread


def _ready_snap(profile, *, ticker="NVDA", last=188.2) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["quotes"],
        source="manual",
        primary_ticker=ticker,
        objective="read NVDA",
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={ticker: {"last": last}}
    )
    return snap


@pytest.mark.django_db
def test_pinned_snapshot_thread_includes_coach_block_on_first_turn():
    profile = TradingProfile.objects.create(name="p", style="s")
    snap = _ready_snap(profile)
    Thesis.objects.create(
        title="AI capex",
        ticker="NVDA",
        direction="bullish",
        conviction=4,
        status="open",
        target_price=210,
    )
    resp = APIClient().post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": snap.id},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    thread = Thread.objects.get(id=resp.json()["id"])
    text = Message.objects.filter(thread=thread, role="user").get().content["text"]
    assert "🧭 What you already know" in text
    assert "AI capex" in text
    assert "read NVDA" in text  # serialize_for_ai payload still present (prepended, not replaced)


@pytest.mark.django_db
def test_disabled_profile_thread_has_no_coach_block():
    profile = TradingProfile.objects.create(name="p", style="s", enable_coach=False)
    snap = _ready_snap(profile)
    Thesis.objects.create(
        title="x", ticker="NVDA", direction="bullish", conviction=4, status="open"
    )
    resp = APIClient().post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": snap.id},
        format="json",
    )
    text = Message.objects.filter(thread__id=resp.json()["id"], role="user").get().content["text"]
    assert "🧭" not in text


@pytest.mark.django_db
def test_follow_up_send_has_no_coach_block():
    profile = TradingProfile.objects.create(name="p", style="s")
    snap = _ready_snap(profile)
    create = APIClient().post(
        "/api/threads/",
        data={"kind": "consult", "profile_id": profile.id, "pinned_snapshot_id": snap.id},
        format="json",
    )
    tid = create.json()["id"]
    with patch("apps.threads.views.run_ai_on_message"):
        send = APIClient().post(
            f"/api/threads/{tid}/send/", data={"text": "what next?"}, format="json"
        )
    assert send.status_code == 202
    follow = Message.objects.get(id=send.json()["id"])
    assert follow.content["text"] == "what next?"  # plain follow-up, no block


@pytest.mark.django_db
def test_observer_fire_includes_coach_block():
    profile = TradingProfile.objects.create(name="P", style="x")
    sched = ObserverSchedule.objects.create(
        name="hourly", profile=profile, market_hours_only=False, objective_template="What changed?"
    )
    snap = _ready_snap(profile)
    Thesis.objects.create(
        title="AI capex", ticker="NVDA", direction="bullish", conviction=4, status="open"
    )
    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.capture", return_value=snap),
        patch("apps.observer.services.run.run_ai_on_message"),
    ):
        run_observer(sched.id)
    thread = Thread.objects.get(profile=profile, kind="observer")
    user_msg = thread.messages.filter(role="user").get()
    assert "🧭 What you already know" in user_msg.content["text"]
    assert "AI capex" in user_msg.content["text"]
