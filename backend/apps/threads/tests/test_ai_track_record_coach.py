"""Coach injects the AI's OWN live track record (M13 F4) — the loop-closing block."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.predictions.models import AIPrediction
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.threads.coach import (
    _ai_track_record_block,
    assemble_coach_context,
    assemble_coach_context_for_message,
)

_NOW = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)


def _profile(model="claude-opus-4-8", **kw) -> TradingProfile:
    return TradingProfile.objects.create(
        name="p", style="s", default_model=model, enable_coach=True, **kw
    )


def _resolved(ticker, verdict, confidence, *, model="claude-opus-4-8"):
    return AIPrediction.objects.create(
        ticker=ticker,
        direction="bullish",
        horizon_days=7,
        confidence=confidence,
        provider="claude",
        model=model,
        predicted_at=_NOW - timedelta(days=7),
        resolve_at=_NOW,
        status="resolved",
        verdict=verdict,
        forward_return_pct=5.0 if verdict == "correct" else -5.0,
        resolved_at=_NOW,
    )


@pytest.mark.django_db
class TestAITrackRecordBlock:
    def test_empty_below_min_sample(self):
        _resolved("NVDA", "correct", 0.7)  # only 1 decisive call
        assert _ai_track_record_block("NVDA", _profile()) == ""

    def test_renders_hit_rate(self):
        for v in ("correct", "correct", "incorrect"):
            _resolved("NVDA", v, 0.7)
        out = _ai_track_record_block("NVDA", _profile())
        assert "My own track record here" in out
        assert "2/3 correct (67%)" in out

    def test_flags_overconfidence(self):
        for v in ("correct", "incorrect", "incorrect"):
            _resolved("NVDA", v, 0.9)  # mean conf 0.9 but 33% realized
        assert "OVER-confident" in _ai_track_record_block("NVDA", _profile())

    def test_scoped_to_profile_model(self):
        for _ in range(3):
            _resolved("NVDA", "correct", 0.7, model="gpt-5")  # different model
        assert _ai_track_record_block("NVDA", _profile(model="claude-opus-4-8")) == ""

    def test_no_model_returns_empty(self):
        for _ in range(3):
            _resolved("NVDA", "correct", 0.7)
        assert _ai_track_record_block("NVDA", _profile(model="")) == ""

    def test_integrates_into_snapshot_coach(self):
        p = _profile()
        snap = Snapshot.objects.create(
            profile=p, status="ready", includes=["quotes"], source="manual", primary_ticker="NVDA"
        )
        SnapshotSection.objects.create(
            snapshot=snap, kind="quotes", status="done", payload={"NVDA": {"last": 100}}
        )
        for _ in range(3):
            _resolved("NVDA", "correct", 0.7)
        assert "My own track record here" in assemble_coach_context(snap, p)

    def test_integrates_into_snapshot_free_coach(self):
        p = _profile()
        for _ in range(3):
            _resolved("NVDA", "correct", 0.7)
        assert "My own track record here" in assemble_coach_context_for_message(
            "thoughts on $NVDA?", p
        )
