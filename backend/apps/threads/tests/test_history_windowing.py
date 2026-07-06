"""Provider-request history hygiene.

Two invariants of ``_history_messages`` / ``_build_request``:

1. Observer threads are append-only per profile (one synthetic snapshot turn per
   fire, never pruned), so the request history MUST be windowed — otherwise fire
   N replays all N-1 prior serialized snapshots, growing input cost linearly
   until the request exceeds the model context window and every fire fails.

2. Compare branches all answer ONE shared user turn. A sibling branch's finished
   reply must never leak into another branch's request (it would bias the
   comparison and, as a trailing assistant turn, act as a prefill), and a
   follow-up send must not replay N branch answers as consecutive assistant turns.
"""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads._request import OBSERVER_HISTORY_TURNS, _build_request
from apps.threads.models import Message, Thread


@pytest.fixture
def profile(db) -> TradingProfile:
    # enable_coach=False keeps the snapshot-free coach path (embedding inference)
    # out of these request-shape tests.
    return TradingProfile.objects.create(name="P", style="You trade.", enable_coach=False)


def _ready_snapshot(profile: TradingProfile) -> Snapshot:
    return Snapshot.objects.create(
        profile=profile,
        objective="obs",
        status="ready",
        includes=["quotes"],
        source="observer",
    )


def _observer_thread_with_fires(profile: TradingProfile, n_fires: int) -> tuple[Thread, Message]:
    """An observer thread with n_fires completed fires; returns (thread, last user msg)."""
    t = Thread.objects.create(kind="observer", profile=profile, title="Observer: P")
    snap = _ready_snapshot(profile)
    last_user = None
    for i in range(n_fires):
        last_user = Message.objects.create(
            thread=t,
            role="user",
            content={"text": f"serialized snapshot {i}"},
            snapshot_ref=snap,
            status="done",
        )
        if i < n_fires - 1:  # the current fire has no reply yet
            Message.objects.create(
                thread=t, role="assistant", content={"text": f"observation {i}"}, status="done"
            )
    assert last_user is not None
    return t, last_user


@pytest.mark.django_db
def test_observer_request_size_does_not_grow_with_fire_count(profile):
    t_small, u_small = _observer_thread_with_fires(profile, 4)
    req_small = _build_request(t_small, u_small)

    t_big, u_big = _observer_thread_with_fires(profile, 25)
    req_big = _build_request(t_big, u_big)

    assert len(req_big.messages) == len(req_small.messages)
    assert len(req_big.messages) <= OBSERVER_HISTORY_TURNS + 1
    # The current fire's synthetic turn is always the final user turn.
    assert req_big.messages[-1].role == "user"
    assert req_big.messages[-1].content == "serialized snapshot 24"
    # Oldest fires fell out of the window.
    contents = [m.content for m in req_big.messages]
    assert "serialized snapshot 0" not in contents
    assert "observation 0" not in contents


@pytest.mark.django_db
def test_observer_window_starts_with_a_user_turn(profile):
    t, u = _observer_thread_with_fires(profile, 10)
    req = _build_request(t, u)
    assert req.messages, "window must not be empty"
    assert req.messages[0].role == "user"


@pytest.mark.django_db
def test_non_observer_thread_keeps_full_history(profile):
    t = Thread.objects.create(kind="chat", profile=profile, title="x")
    for i in range(8):
        Message.objects.create(thread=t, role="user", content={"text": f"q{i}"}, status="done")
        Message.objects.create(thread=t, role="assistant", content={"text": f"a{i}"}, status="done")
    u = Message.objects.create(thread=t, role="user", content={"text": "final"}, status="done")
    req = _build_request(t, u)
    assert len(req.messages) == 17  # 8 exchanges + the new user turn


@pytest.mark.django_db
def test_compare_branch_request_excludes_sibling_branch_replies(profile):
    t = Thread.objects.create(kind="chat", profile=profile, title="x")
    Message.objects.create(thread=t, role="user", content={"text": "earlier q"}, status="done")
    Message.objects.create(thread=t, role="assistant", content={"text": "earlier a"}, status="done")
    u = Message.objects.create(
        thread=t, role="user", content={"text": "compare this"}, status="done"
    )
    # Two branches finished before the third builds its request (busy worker pool).
    Message.objects.create(
        thread=t,
        role="assistant",
        content={"text": "claude branch answer"},
        status="done",
        parent_message=u,
    )
    Message.objects.create(
        thread=t,
        role="assistant",
        content={"text": "openai branch answer"},
        status="done",
        parent_message=u,
    )

    req = _build_request(t, u)

    contents = [m.content for m in req.messages]
    assert "claude branch answer" not in contents
    assert "openai branch answer" not in contents
    # The shared user turn is the final message — no trailing sibling prefill.
    assert req.messages[-1].role == "user"
    assert req.messages[-1].content == "compare this"
    assert contents == ["earlier q", "earlier a", "compare this"]


@pytest.mark.django_db
def test_followup_send_after_compare_excludes_all_branch_replies(profile):
    t = Thread.objects.create(kind="chat", profile=profile, title="x")
    u = Message.objects.create(
        thread=t, role="user", content={"text": "compare this"}, status="done"
    )
    for name in ("claude", "openai", "local"):
        Message.objects.create(
            thread=t,
            role="assistant",
            content={"text": f"{name} branch answer"},
            status="done",
            parent_message=u,
        )
    followup = Message.objects.create(
        thread=t, role="user", content={"text": "follow-up"}, status="done"
    )

    req = _build_request(t, followup)

    assert [m.content for m in req.messages] == ["compare this", "follow-up"]
