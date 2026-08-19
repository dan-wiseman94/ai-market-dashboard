from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.thesis.models import Thesis
from apps.threads.coach import (
    _calibration_block,
    _calibration_verdict,
    assemble_coach_context,
    build_system_prompt,
)

NOW = datetime(2026, 5, 29, 14, 30, tzinfo=UTC)


@pytest.mark.django_db
def test_system_prompt_wraps_style_and_includes_date_when_enabled():
    p = TradingProfile.objects.create(name="p", style="Aggressive intraday")
    out = build_system_prompt(p, now=NOW)
    assert "Aggressive intraday" in out
    assert "observational" in out.lower()
    assert "2026-05-29" in out


@pytest.mark.django_db
def test_system_prompt_is_style_under_boundary_when_coach_disabled():
    # Coach off = the "just your style" framing, but the untrusted-content data
    # boundary (prompt-injection defense) is always prepended.
    p = TradingProfile.objects.create(name="p", style="Aggressive intraday", enable_coach=False)
    system = build_system_prompt(p, now=NOW)
    assert "Data boundary" in system
    assert system.endswith("Aggressive intraday")
    assert "## Your trading style" not in system  # no coach framing when disabled


def test_system_prompt_none_profile_is_just_boundary():
    system = build_system_prompt(None, now=NOW)
    assert "Data boundary" in system
    assert "UNTRUSTED CONTENT" in system


@pytest.mark.django_db
def test_system_prompt_omits_style_header_when_style_is_blank():
    p = TradingProfile.objects.create(name="p", style="")
    out = build_system_prompt(p, now=NOW)
    assert "observational" in out.lower()
    assert "## Your trading style" not in out


@pytest.fixture
def coach_profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="c", style="s")


def _snap(profile, *, ticker="NVDA", last=188.2) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["quotes"],
        source="manual",
        primary_ticker=ticker,
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={ticker: {"last": last}}
    )
    return snap


@pytest.mark.django_db
def test_coach_empty_when_disabled(coach_profile):
    coach_profile.enable_coach = False
    coach_profile.save()
    assert assemble_coach_context(_snap(coach_profile), coach_profile) == ""


@pytest.mark.django_db
def test_coach_empty_without_primary_ticker(coach_profile):
    snap = Snapshot.objects.create(
        profile=coach_profile, status="ready", includes=["quotes"], source="manual"
    )
    assert snap.primary_ticker is None
    assert assemble_coach_context(snap, coach_profile) == ""


@pytest.mark.django_db
def test_coach_empty_when_no_history(coach_profile):
    # primary_ticker set, but no theses / no prior snapshot / no recall / no track record
    assert assemble_coach_context(_snap(coach_profile), coach_profile) == ""


@pytest.mark.django_db
def test_coach_includes_open_thesis_with_header(coach_profile):
    Thesis.objects.create(
        title="AI capex",
        ticker="NVDA",
        direction="bullish",
        conviction=4,
        status="open",
        target_price=210,
    )
    out = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert "🧭 What you already know" in out
    assert "Open theses on NVDA" in out
    assert "AI capex" in out


@pytest.mark.django_db
def test_coach_includes_diff_vs_prior(coach_profile):
    prior = _snap(coach_profile, last=181.1)  # prior ready snapshot, same ticker
    # Pin captured_at strictly earlier — previous_snapshot_for uses captured_at__lt,
    # and two auto_now_add rows could otherwise collide on timestamp (flaky).
    Snapshot.objects.filter(pk=prior.pk).update(captured_at=timezone.now() - timedelta(hours=1))
    curr = _snap(coach_profile, last=188.2)
    out = assemble_coach_context(curr, coach_profile)
    assert "Since your last look" in out


@pytest.mark.django_db
def test_coach_caps_open_theses_at_three(coach_profile):
    for i in range(5):
        Thesis.objects.create(
            title=f"thesis-{i}",
            ticker="NVDA",
            direction="bullish",
            conviction=3,
            status="open",
        )
    out = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert out.count("[bullish · conviction") == 3


@pytest.mark.django_db
def test_coach_never_raises_when_a_subsource_throws(coach_profile, monkeypatch):
    Thesis.objects.create(
        title="AI capex", ticker="NVDA", direction="bullish", conviction=4, status="open"
    )

    def boom(*a, **k):
        raise RuntimeError("recall is down")

    monkeypatch.setattr("apps.threads.coach.related_to_situation", boom)
    out = assemble_coach_context(_snap(coach_profile), coach_profile)  # must NOT raise
    assert "Open theses on NVDA" in out  # the healthy section still renders


@pytest.mark.django_db
def test_recall_block_uses_situation_search(coach_profile, monkeypatch):
    from apps.threads import coach as coach_mod

    snap = _snap(coach_profile)  # primary_ticker NVDA, quotes section last=188.2
    captured = {}

    def fake(ticker, query, *, k, kinds):
        captured["ticker"] = ticker
        captured["query"] = query
        captured["k"] = k
        captured["kinds"] = kinds
        return [
            {
                "kind": "postmortem",
                "object_id": 7,
                "snippet": "NVDA ran into earnings",
                "source_created_at": NOW,
                "tickers": ["NVDA"],
                "link": "/theses/7",
            }
        ]

    monkeypatch.setattr(coach_mod, "related_to_situation", fake)
    out = coach_mod._recall_block(snap, "NVDA")

    assert captured["ticker"] == "NVDA"
    assert "NVDA" in captured["query"]
    assert captured["k"] == coach_mod._MAX_RECALL_ITEMS
    assert set(captured["kinds"]) == {"postmortem", "thesis", "observation"}
    assert "### You've noted this before" in out
    assert "NVDA ran into earnings" in out


@pytest.mark.django_db
def test_recall_block_empty_ticker_returns_empty(coach_profile):
    from apps.threads.coach import _recall_block

    assert _recall_block(_snap(coach_profile), "") == ""


@pytest.mark.django_db
def test_lessons_block_renders_decisive_postmortems(coach_profile):
    from apps.thesis.models import PostMortem, Thesis
    from apps.threads.coach import _lessons_block

    t = Thesis.objects.create(
        title="Earnings run",
        ticker="NVDA",
        direction="bullish",
        conviction=4,
        status="closed_loss",
    )
    pm = PostMortem.objects.create(
        thesis=t,
        horizon_days=30,
        due_at=NOW,
        status="done",
        verdict="incorrect",
        forward_return_pct=-5.0,
        report={
            "lessons": ["Size smaller into earnings", "Wait for the IV crush"],
            "what_missed": ["Guidance was already priced in"],
        },
    )
    PostMortem.objects.filter(pk=pm.pk).update(completed_at=NOW)

    out = _lessons_block("NVDA")
    assert "### Lessons learned" in out
    assert "incorrect" in out
    assert "30d" in out
    assert "Size smaller into earnings" in out
    assert "Wait for the IV crush" in out  # 2nd bullet (cap = 2)
    assert "Guidance was already priced in" not in out  # 3rd bullet dropped by _MAX_LESSON_BULLETS


@pytest.mark.django_db
def test_lessons_block_ignores_inconclusive_and_unfinished(coach_profile):
    from apps.thesis.models import PostMortem, Thesis
    from apps.threads.coach import _lessons_block

    t = Thesis.objects.create(
        title="x", ticker="NVDA", direction="bullish", conviction=3, status="open"
    )
    PostMortem.objects.create(  # inconclusive -> excluded
        thesis=t,
        horizon_days=7,
        due_at=NOW,
        status="done",
        verdict="inconclusive",
        report={"lessons": ["nope"]},
    )
    PostMortem.objects.create(  # still scheduled -> excluded
        thesis=t,
        horizon_days=90,
        due_at=NOW,
        status="scheduled",
        verdict="correct",
        report={"lessons": ["also nope"]},
    )
    PostMortem.objects.create(  # mixed -> excluded (only correct/incorrect are decisive)
        thesis=t,
        horizon_days=30,
        due_at=NOW,
        status="done",
        verdict="mixed",
        report={"lessons": ["still nope"]},
    )
    assert _lessons_block("NVDA") == ""


@pytest.mark.django_db
def test_lessons_block_caps_at_two(coach_profile):
    from apps.thesis.models import PostMortem, Thesis
    from apps.threads.coach import _lessons_block

    for i in range(4):
        t = Thesis.objects.create(
            title=f"t{i}", ticker="NVDA", direction="bullish", conviction=3, status="open"
        )
        pm = PostMortem.objects.create(
            thesis=t,
            horizon_days=30,
            due_at=NOW,
            status="done",
            verdict="correct",
            forward_return_pct=4.0,
            report={"lessons": [f"lesson {i}"]},
        )
        PostMortem.objects.filter(pk=pm.pk).update(completed_at=NOW)
    out = _lessons_block("NVDA")
    # At most 2 post-mortem bullet headers (one per pm) rendered.
    assert out.count("[correct, 30d]") == 2


def test_lessons_block_empty_ticker():
    from apps.threads.coach import _lessons_block

    assert _lessons_block("") == ""


def test_calibration_verdict_overconfident():
    # observed < stated in both buckets -> overconfident
    buckets = [
        {"n": 2, "observed_hit_rate": 0.5, "mean_confidence": 0.9},
        {"n": 1, "observed_hit_rate": 0.6, "mean_confidence": 0.8},
    ]
    assert "OVER-confident" in _calibration_verdict(buckets)


def test_calibration_verdict_underconfident():
    buckets = [{"n": 3, "observed_hit_rate": 0.9, "mean_confidence": 0.6}]
    assert "UNDER-confident" in _calibration_verdict(buckets)


def test_calibration_verdict_well_calibrated():
    buckets = [{"n": 3, "observed_hit_rate": 0.72, "mean_confidence": 0.70}]
    assert "well-calibrated" in _calibration_verdict(buckets)


def test_calibration_verdict_none_when_no_usable_buckets():
    assert (
        _calibration_verdict([{"n": 0, "observed_hit_rate": None, "mean_confidence": None}]) is None
    )


@pytest.mark.django_db
def test_calibration_block_renders_latest_run(coach_profile):
    from apps.analytics.services.aieval import persist_eval_run

    persist_eval_run(
        {
            "label": "scheduled",
            "model": coach_profile.default_model,
            "n": 10,
            "scored": 8,
            "hit_rate": 0.625,
            "brier": 0.22,
            "calibration": [{"n": 8, "observed_hit_rate": 0.5, "mean_confidence": 0.85}],
        },
        source="scheduled",
    )
    block = _calibration_block(coach_profile)
    assert "Model calibration" in block
    assert "62%" in block or "63%" in block  # 0.625 hit-rate as a percentage
    assert "OVER-confident" in block


@pytest.mark.django_db
def test_calibration_block_empty_when_no_run(coach_profile):
    assert _calibration_block(coach_profile) == ""


@pytest.mark.django_db
def test_calibration_block_empty_for_mismatched_model(coach_profile):
    from apps.analytics.services.aieval import persist_eval_run

    persist_eval_run(
        {"label": "x", "model": "a-totally-different-model", "n": 5, "scored": 5, "hit_rate": 0.8},
        source="manual",
    )
    # coach_profile.default_model differs from the only EvalRun's model -> no block
    assert _calibration_block(coach_profile) == ""


@pytest.mark.django_db
def test_assemble_coach_context_includes_calibration(coach_profile):
    from apps.analytics.services.aieval import persist_eval_run

    persist_eval_run(
        {
            "label": "scheduled",
            "model": coach_profile.default_model,
            "n": 6,
            "scored": 6,
            "hit_rate": 0.66,
            "brier": 0.2,
            "calibration": [{"n": 6, "observed_hit_rate": 0.66, "mean_confidence": 0.66}],
        },
        source="scheduled",
    )
    ctx = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert "Model calibration" in ctx


@pytest.mark.django_db
def test_assemble_includes_lessons_block(coach_profile):
    from apps.thesis.models import PostMortem, Thesis

    t = Thesis.objects.create(
        title="y", ticker="NVDA", direction="bearish", conviction=2, status="closed_win"
    )
    pm = PostMortem.objects.create(
        thesis=t,
        horizon_days=90,
        due_at=NOW,
        status="done",
        verdict="correct",
        forward_return_pct=8.0,
        report={"lessons": ["Trust the breadth signal"]},
    )
    PostMortem.objects.filter(pk=pm.pk).update(completed_at=NOW)

    out = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert "🧭 What you already know" in out
    assert "### Lessons learned" in out
    assert "Trust the breadth signal" in out


@pytest.mark.django_db
def test_w5_coach_gate_parity(coach_profile):
    """W5: assemble_coach_context is the single enable_coach/primary_ticker gate
    that all three injection sites (threads view, observer, trigger) call."""
    Thesis.objects.create(
        title="AI capex",
        ticker="NVDA",
        direction="bullish",
        conviction=4,
        status="open",
        target_price=210,
    )
    snap = _snap(coach_profile)  # primary_ticker=NVDA

    # enable_coach defaults True for coach_profile -> block present.
    on_out = assemble_coach_context(snap, coach_profile)
    assert "🧭 What you already know" in on_out
    assert "Open theses on NVDA" in on_out

    # Flip the flag -> the same call returns "" (no per-site divergence possible).
    coach_profile.enable_coach = False
    coach_profile.save()
    assert assemble_coach_context(snap, coach_profile) == ""

    # No primary ticker -> "" regardless of flag (the other gate).
    coach_profile.enable_coach = True
    coach_profile.save()
    blank = Snapshot.objects.create(
        profile=coach_profile, status="ready", includes=["quotes"], source="manual"
    )
    assert blank.primary_ticker is None
    assert assemble_coach_context(blank, coach_profile) == ""
