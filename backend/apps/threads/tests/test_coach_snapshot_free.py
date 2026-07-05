"""Coach on snapshot-free chat (message-keyed) + per-turn refresh.

The snapshot-bearing coach returns "" with no primary_ticker, so without a
message-keyed block a snapshot-free chat would get no coach context.
assemble_coach_context_for_message sources the situation from the message text
instead, and _build_request injects it per turn — but only for threads with no
snapshot-bearing turn, so it never double-injects.
"""

from __future__ import annotations

from unittest.mock import patch

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.threads._request import _build_request, _is_snapshot_free
from apps.threads.coach import _ticker_from_text, assemble_coach_context_for_message
from apps.threads.models import Message, Thread

HITS = [
    {"kind": "thesis", "snippet": "AI capex thesis", "link": "/theses/1", "source_created_at": None}
]


def _profile(**kw) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s", **kw)


def _snap(profile) -> Snapshot:
    return Snapshot.objects.create(
        profile=profile, status="ready", includes=["quotes"], source="manual", primary_ticker="NVDA"
    )


class TestTickerFromText:
    def test_extracts_cashtag(self) -> None:
        assert _ticker_from_text("thoughts on $NVDA into earnings?") == "NVDA"

    def test_lowercase_cashtag_is_upcased(self) -> None:
        assert _ticker_from_text("watching $aapl") == "AAPL"

    def test_none_without_cashtag(self) -> None:
        assert _ticker_from_text("should I sell my position?") is None

    def test_none_for_empty(self) -> None:
        assert _ticker_from_text("") is None


class TestAssembleForMessage:
    def test_disabled_profile_returns_empty(self, db) -> None:
        p = _profile(enable_coach=False)
        with patch("apps.threads.coach.search", return_value=HITS):
            assert assemble_coach_context_for_message("$NVDA hello", p) == ""

    def test_empty_text_returns_empty(self, db) -> None:
        p = _profile(enable_coach=True)
        assert assemble_coach_context_for_message("   ", p) == ""

    def test_recall_hits_populate_block_scoped_to_cashtag(self, db) -> None:
        p = _profile(enable_coach=True)
        with patch("apps.threads.coach.search", return_value=HITS) as s:
            out = assemble_coach_context_for_message("what's up with $NVDA?", p)
        assert "🧭 What you already know" in out
        assert "You've noted this before" in out
        assert "AI capex thesis" in out
        assert s.call_args.kwargs["ticker"] == "NVDA"

    def test_no_cashtag_searches_unscoped(self, db) -> None:
        p = _profile(enable_coach=True)
        with patch("apps.threads.coach.search", return_value=HITS) as s:
            assemble_coach_context_for_message("how is the market mood today?", p)
        assert s.call_args.kwargs["ticker"] is None

    def test_empty_when_no_subblocks(self, db) -> None:
        p = _profile(enable_coach=True)
        with patch("apps.threads.coach.search", return_value=[]):
            assert assemble_coach_context_for_message("hi there", p) == ""

    def test_cashtag_includes_lessons(self, db) -> None:
        from datetime import UTC, datetime

        from apps.thesis.models import PostMortem, Thesis

        th = Thesis.objects.create(
            title="AI capex", ticker="NVDA", direction="bullish", conviction=4, status="closed"
        )
        PostMortem.objects.create(
            thesis=th,
            horizon_days=30,
            due_at=datetime(2026, 3, 1, tzinfo=UTC),
            status="done",
            verdict="correct",
            report={"lessons": ["entry was late"]},
        )
        p = _profile(enable_coach=True)
        with patch("apps.threads.coach.search", return_value=[]):
            out = assemble_coach_context_for_message("revisit $NVDA", p)
        assert "Lessons learned" in out
        assert "AI capex" in out


class TestBuildRequestInjection:
    def test_snapshot_free_thread_gets_coach_in_system(self, db) -> None:
        p = _profile(enable_coach=True)
        t = Thread.objects.create(profile=p, kind="consult")
        m = Message.objects.create(
            thread=t, role="user", content={"text": "$NVDA outlook?"}, status="done"
        )
        with patch("apps.threads.coach.search", return_value=HITS):
            req = _build_request(t, m, provider_name="claude")
        assert "🧭 What you already know" in req.system

    def test_snapshot_bearing_thread_has_no_message_keyed_coach(self, db) -> None:
        # The create-time snapshot coach owns these threads; the message-keyed one
        # must stay out to avoid double-injection.
        p = _profile(enable_coach=True)
        snap = _snap(p)
        t = Thread.objects.create(profile=p, kind="consult")
        m = Message.objects.create(
            thread=t, role="user", content={"text": "$NVDA"}, status="done", snapshot_ref=snap
        )
        with patch("apps.threads.coach.search", return_value=HITS):
            req = _build_request(t, m, provider_name="claude")
        assert "🧭 What you already know" not in req.system

    def test_is_snapshot_free_false_when_history_has_snapshot(self, db) -> None:
        p = _profile(enable_coach=True)
        snap = _snap(p)
        t = Thread.objects.create(profile=p, kind="consult")
        first = Message.objects.create(
            thread=t, role="user", content={"text": "x"}, status="done", snapshot_ref=snap
        )
        follow = Message.objects.create(
            thread=t, role="user", content={"text": "$AAPL?"}, status="done"
        )
        assert _is_snapshot_free([first], follow) is False

    def test_per_turn_refresh_uses_latest_message(self, db) -> None:
        # The coach is recomputed from the CURRENT user turn, not frozen at create.
        p = _profile(enable_coach=True)
        t = Thread.objects.create(profile=p, kind="consult")
        Message.objects.create(thread=t, role="user", content={"text": "$NVDA"}, status="done")
        Message.objects.create(thread=t, role="assistant", content={"text": "..."}, status="done")
        latest = Message.objects.create(
            thread=t, role="user", content={"text": "now what about $TSLA"}, status="done"
        )
        with patch("apps.threads.coach.search", return_value=HITS) as s:
            _build_request(t, latest, provider_name="claude")
        assert s.call_args.kwargs["ticker"] == "TSLA"

    def test_disabled_profile_no_coach_in_system(self, db) -> None:
        p = _profile(enable_coach=False)
        t = Thread.objects.create(profile=p, kind="consult")
        m = Message.objects.create(thread=t, role="user", content={"text": "$NVDA?"}, status="done")
        with patch("apps.threads.coach.search", return_value=HITS):
            req = _build_request(t, m, provider_name="claude")
        assert "🧭 What you already know" not in req.system
