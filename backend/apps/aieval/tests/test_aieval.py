"""Tests for the offline AI evaluation harness (apps.aieval).

Mock-only: ``run_structured`` is patched to a controlled ``ObservationReport``
so scoring is hand-checkable and no real model is ever called (free + deterministic).
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.aieval import services as svc
from apps.aieval.services import (
    _confidence_from_report,
    confidence_calibration,
    evaluate,
    labeled_examples,
    persist_eval_run,
    replay_one,
)
from apps.observer.schemas import ObservationReport, Signal
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.thesis.models import PostMortem, Thesis


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(
        name="Eval", style="swing trader", default_provider="claude"
    )


def _snapshot(profile, ticker="AAPL"):
    s = Snapshot.objects.create(
        profile=profile, includes=["quotes"], source="manual", status="ready"
    )
    s.sections.create(
        kind="quotes",
        payload={ticker: {"last": 150.0, "pct_change": 1.2}},
        status="done",
    )
    return s


def _thesis(profile, *, direction="bullish", conviction=3, snapshot=None, ticker="AAPL"):
    return Thesis.objects.create(
        title=f"{direction} {ticker}",
        ticker=ticker,
        direction=direction,
        conviction=conviction,
        profile=profile,
        snapshot=snapshot,
        opened_at=timezone.now() - timedelta(days=120),
    )


def _postmortem(thesis, *, verdict="correct", fwd=5.0, status="done", horizon=30):
    return PostMortem.objects.create(
        thesis=thesis,
        horizon_days=horizon,
        due_at=thesis.opened_at + timedelta(days=horizon),
        status=status,
        verdict=verdict,
        forward_return_pct=fwd,
    )


def _report(bias="bullish", confs=(0.8,)):
    return ObservationReport(
        headline="h",
        bias=bias,
        summary="s",
        signals=[
            Signal(ticker="AAPL", bias=bias, thesis="t", invalidation="i", confidence=c)
            for c in confs
        ],
        next_check_in="tomorrow",
    )


# --------------------------------------------------------------------------- #
# Commit 1 — labeled_examples selector
# --------------------------------------------------------------------------- #
def test_labeled_examples_returns_only_decisive_with_snapshot(profile):
    snap = _snapshot(profile)
    good = _postmortem(_thesis(profile, snapshot=snap), verdict="correct", fwd=5.0)

    # Non-decisive / unusable rows that must be EXCLUDED:
    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="inconclusive", fwd=None)
    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="mixed", fwd=0.3)
    _postmortem(_thesis(profile, snapshot=None), verdict="correct", fwd=4.0)  # no snapshot
    # decisive + snapshot but still scheduled (not done) -> excluded
    _postmortem(
        _thesis(profile, snapshot=_snapshot(profile)),
        verdict="correct",
        fwd=4.0,
        status="scheduled",
    )

    rows = labeled_examples()
    assert [pm.id for pm in rows] == [good.id]


def test_labeled_examples_limit_caps(profile):
    for _ in range(3):
        _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    assert len(labeled_examples()) == 3
    assert len(labeled_examples(limit=2)) == 2


def test_labeled_examples_horizon_filters(profile):
    _postmortem(
        _thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0, horizon=7
    )
    _postmortem(
        _thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0, horizon=30
    )
    assert len(labeled_examples(horizon=7)) == 1
    assert len(labeled_examples(horizon=30)) == 1


# --------------------------------------------------------------------------- #
# Commit 2 — replay_one + evaluate (mock mode)
# --------------------------------------------------------------------------- #
def test_replay_one_extracts_direction_confidence_and_hit(profile):
    snap = _snapshot(profile)
    pm = _postmortem(
        _thesis(profile, direction="bullish", snapshot=snap), verdict="correct", fwd=5.0
    )
    # model says bullish; outcome (correct bullish thesis) is bullish -> hit
    with patch.object(svc, "run_structured", return_value=_report("bullish", confs=(0.6, 1.0))):
        r = replay_one(pm, system="sys", model="claude-opus-4-8")
    assert r["predicted_direction"] == "bullish"
    assert r["outcome_direction"] == "bullish"
    assert r["hit"] is True
    assert r["confidence"] == 0.8  # mean(0.6, 1.0)


def test_replay_one_miss_when_model_wrong(profile):
    snap = _snapshot(profile)
    # thesis bullish + verdict incorrect => the market actually went bearish.
    pm = _postmortem(
        _thesis(profile, direction="bullish", snapshot=snap), verdict="incorrect", fwd=-5.0
    )
    with patch.object(svc, "run_structured", return_value=_report("bullish")):
        r = replay_one(pm, system="sys", model="claude-opus-4-8")
    assert r["outcome_direction"] == "bearish"
    assert r["hit"] is False


def test_replay_one_is_look_ahead_safe_no_coach(profile):
    """The user turn handed to run_structured must be ONLY the serialized
    snapshot — no coach/recall/post-trade context (look-ahead boundary)."""
    snap = _snapshot(profile)
    pm = _postmortem(_thesis(profile, snapshot=snap), verdict="correct", fwd=5.0)
    from apps.snapshots.serializer import serialize_for_ai

    expected = serialize_for_ai(snap, provider="claude", model="claude-opus-4-8")
    with patch.object(svc, "run_structured", return_value=_report()) as m:
        replay_one(pm, system="sys", model="claude-opus-4-8")
    user_arg = m.call_args.kwargs["user"]
    assert user_arg == expected  # byte-for-byte the bare snapshot
    assert "Track record" not in user_arg and "post-mortem" not in user_arg.lower()


def test_evaluate_hit_rate_and_brier_hand_checkable(profile):
    # Three decisive examples, all conviction=3 -> prob = 0.5 + (3-1)/4*0.4 = 0.7
    # ex1: thesis bullish/correct (outcome bullish), model bullish -> HIT,  o=1
    # ex2: thesis bullish/correct (outcome bullish), model bearish -> MISS, o=0
    # ex3: thesis bearish/incorrect (outcome bullish), model bullish -> HIT, o=1
    snap = _snapshot(profile)
    e1 = _postmortem(
        _thesis(profile, direction="bullish", conviction=3, snapshot=snap),
        verdict="correct",
        fwd=5.0,
    )
    e2 = _postmortem(
        _thesis(profile, direction="bullish", conviction=3, snapshot=_snapshot(profile)),
        verdict="correct",
        fwd=5.0,
    )
    e3 = _postmortem(
        _thesis(profile, direction="bearish", conviction=3, snapshot=_snapshot(profile)),
        verdict="incorrect",
        fwd=5.0,
    )

    # Drive deterministic per-call replies in id order (labeled_examples orders by id).
    assert [e1.id, e2.id, e3.id] == sorted([e1.id, e2.id, e3.id])  # ids ascending
    ordered = [
        _report("bullish", confs=(1.0,)),  # e1 -> hit
        _report("bearish", confs=(0.5,)),  # e2 -> miss
        _report("bullish", confs=(0.6,)),  # e3 -> hit
    ]
    with patch.object(svc, "run_structured", side_effect=ordered):
        res = evaluate(system="sys", model="claude-opus-4-8", label="cand")

    assert res["n"] == 3
    assert res["scored"] == 3
    assert res["skipped"] == 0
    # hit_rate = 2 correct / 3 = 0.6667
    assert res["hit_rate"] == round(2 / 3, 4)
    # brier = mean((p-1)^2, (p-0)^2, (p-1)^2) with p = prob for conviction 3 = 0.7.
    # Compute the expected value the SAME way the code does (avoid rounded literals
    # diverging from float-squared terms): outcomes o = [1, 0, 1].
    p = 0.7
    expected_brier = round(((p - 1) ** 2 + (p - 0) ** 2 + (p - 1) ** 2) / 3, 4)
    assert res["brier"] == expected_brier == 0.2233
    # avg_confidence = mean(1.0, 0.5, 0.6) = 0.7
    assert res["avg_confidence"] == round((1.0 + 0.5 + 0.6) / 3, 4)


def test_evaluate_skips_error_row_never_raises(profile):
    _postmortem(
        _thesis(profile, direction="bullish", snapshot=_snapshot(profile)),
        verdict="correct",
        fwd=5.0,
    )
    _postmortem(
        _thesis(profile, direction="bullish", snapshot=_snapshot(profile)),
        verdict="correct",
        fwd=5.0,
    )

    # First call raises, second returns a hit. evaluate must survive.
    with patch.object(
        svc, "run_structured", side_effect=[RuntimeError("boom"), _report("bullish")]
    ):
        res = evaluate(system="sys", model="claude-opus-4-8", label="cand")
    assert res["skipped"] == 1
    assert res["n"] == 1
    assert res["hit_rate"] == 1.0


def test_evaluate_empty_dataset(profile):
    res = evaluate(system="sys", model="claude-opus-4-8", label="cand")
    assert res["n"] == 0
    assert res["hit_rate"] is None
    assert res["brier"] is None


# --------------------------------------------------------------------------- #
# Commit 3 — management command
# --------------------------------------------------------------------------- #
def test_command_runs_and_prints(profile):
    _postmortem(
        _thesis(profile, direction="bullish", snapshot=_snapshot(profile)),
        verdict="correct",
        fwd=5.0,
    )
    _postmortem(
        _thesis(profile, direction="bullish", snapshot=_snapshot(profile)),
        verdict="correct",
        fwd=5.0,
    )
    out = StringIO()
    with patch.object(svc, "run_structured", return_value=_report("bullish")):
        call_command(
            "aieval", "--model", "claude-opus-4-8", "--limit", "2", "--label", "smoke", stdout=out
        )
    text = out.getvalue()
    assert "variant=smoke" in text
    assert "n=2" in text
    assert "hit_rate=1.0" in text


def test_command_zero_data_friendly_message(db):
    out = StringIO()
    call_command("aieval", "--model", "claude-opus-4-8", stdout=out)
    assert "no labeled data yet" in out.getvalue()


# --------------------------------------------------------------------------- #
# M6-3 — confidence_calibration reliability curve
# --------------------------------------------------------------------------- #


def test_confidence_calibration_bucket_assignment():
    """Hand-checkable: confidences [0.95(hit), 0.92(miss), 0.6(hit), 0.4(hit)].

    Bucket breakdown:
      [0.0, 0.5): confidence=0.4, hit=True -> n=1, hits=1, observed=1.0, mean_conf=0.4
      [0.5, 0.7): confidence=0.6, hit=True -> n=1, hits=1, observed=1.0, mean_conf=0.6
      [0.7, 0.9): no entries           -> n=0, observed=None, mean_conf=None
      [0.9, 1.0): confidence=0.95(hit) and 0.92(miss) -> n=2, hits=1, observed=0.5, mean_conf=round((0.95+0.92)/2,4)=0.935
    """
    results = [
        {"confidence": 0.95, "hit": True},
        {"confidence": 0.92, "hit": False},
        {"confidence": 0.6, "hit": True},
        {"confidence": 0.4, "hit": True},
    ]
    buckets = confidence_calibration(results)
    assert len(buckets) == 4

    b_low = buckets[0]  # [0.0, 0.5)
    assert b_low["bin_low"] == 0.0
    assert b_low["bin_high"] == 0.5
    assert b_low["n"] == 1
    assert b_low["hits"] == 1
    assert b_low["observed_hit_rate"] == 1.0
    assert b_low["mean_confidence"] == 0.4

    b_mid1 = buckets[1]  # [0.5, 0.7)
    assert b_mid1["n"] == 1
    assert b_mid1["hits"] == 1
    assert b_mid1["observed_hit_rate"] == 1.0
    assert b_mid1["mean_confidence"] == 0.6

    b_mid2 = buckets[2]  # [0.7, 0.9) — empty
    assert b_mid2["n"] == 0
    assert b_mid2["observed_hit_rate"] is None
    assert b_mid2["mean_confidence"] is None

    b_high = buckets[3]  # [0.9, 1.0)
    assert b_high["bin_low"] == 0.9
    assert b_high["bin_high"] == 1.0
    assert b_high["n"] == 2
    assert b_high["hits"] == 1
    assert b_high["observed_hit_rate"] == 0.5
    assert b_high["mean_confidence"] == round((0.95 + 0.92) / 2, 4)  # 0.935


def test_confidence_calibration_excludes_none_rows():
    """Rows with confidence=None OR hit=None must be silently excluded."""
    results = [
        {"confidence": None, "hit": True},  # excluded: no confidence
        {"confidence": 0.8, "hit": None},  # excluded: non-directional (no hit)
        {"confidence": 0.8, "hit": True},  # counted: [0.7, 0.9) bucket
        {"confidence": 0.8, "hit": False},  # counted: [0.7, 0.9) bucket
    ]
    buckets = confidence_calibration(results)
    b_mid2 = buckets[2]  # [0.7, 0.9)
    assert b_mid2["n"] == 2
    assert b_mid2["hits"] == 1
    assert b_mid2["observed_hit_rate"] == 0.5

    # Buckets for [0.0,0.5) and [0.5,0.7) and [0.9,1.0) must be empty
    assert buckets[0]["n"] == 0
    assert buckets[1]["n"] == 0
    assert buckets[3]["n"] == 0


def test_confidence_calibration_empty_results():
    """Empty input produces four buckets all with n=0 and None rates."""
    buckets = confidence_calibration([])
    assert len(buckets) == 4
    for b in buckets:
        assert b["n"] == 0
        assert b["observed_hit_rate"] is None
        assert b["mean_confidence"] is None


def test_confidence_calibration_error_hand_checkable():
    """calibration_error = mean abs(observed - mean_conf) over non-empty buckets.

    Using confidences [0.95(hit), 0.92(miss), 0.6(hit), 0.4(hit)]:
      non-empty buckets:
        [0.0,0.5): observed=1.0, mean_conf=0.4 -> abs=0.6
        [0.5,0.7): observed=1.0, mean_conf=0.6 -> abs=0.4
        [0.9,1.0): observed=0.5, mean_conf=0.935 -> abs=0.435
      calibration_error = round((0.6 + 0.4 + 0.435) / 3, 4) = round(1.435/3, 4) = 0.4783
    """
    results = [
        {"confidence": 0.95, "hit": True},
        {"confidence": 0.92, "hit": False},
        {"confidence": 0.6, "hit": True},
        {"confidence": 0.4, "hit": True},
    ]
    buckets = confidence_calibration(results)
    non_empty = [b for b in buckets if b["n"] > 0]
    abs_errors = [abs(b["observed_hit_rate"] - b["mean_confidence"]) for b in non_empty]
    expected_error = round(sum(abs_errors) / len(abs_errors), 4)
    assert expected_error == round((0.6 + 0.4 + 0.435) / 3, 4)  # 0.4783


def test_evaluate_includes_calibration_key(profile):
    """evaluate() must return a 'calibration' key (list of buckets) and
    a 'calibration_error' key. Verified with a minimal dataset."""
    snap = _snapshot(profile)
    _postmortem(
        _thesis(profile, direction="bullish", conviction=3, snapshot=snap),
        verdict="correct",
        fwd=5.0,
    )
    with patch.object(svc, "run_structured", return_value=_report("bullish", confs=(0.85,))):
        res = evaluate(system="sys", model="claude-opus-4-8", label="cal-test")

    assert "calibration" in res
    assert isinstance(res["calibration"], list)
    assert len(res["calibration"]) == 4  # one bucket per _CONF_BINS entry

    # The single hit at confidence=0.85 lands in [0.7, 0.9)
    b_mid2 = res["calibration"][2]
    assert b_mid2["n"] == 1
    assert b_mid2["hits"] == 1
    assert b_mid2["observed_hit_rate"] == 1.0
    assert b_mid2["mean_confidence"] == 0.85

    assert "calibration_error" in res
    # Only one non-empty bucket: abs(1.0 - 0.85) = 0.15
    assert res["calibration_error"] == round(abs(1.0 - 0.85), 4)  # 0.15


def test_command_prints_calibration_table(profile):
    """The management command must print a calibration table when data exists."""
    snap = _snapshot(profile)
    _postmortem(
        _thesis(profile, direction="bullish", conviction=3, snapshot=snap),
        verdict="correct",
        fwd=5.0,
    )
    out = StringIO()
    with patch.object(svc, "run_structured", return_value=_report("bullish", confs=(0.85,))):
        call_command(
            "aieval",
            "--model",
            "claude-opus-4-8",
            "--limit",
            "1",
            "--label",
            "caltest",
            stdout=out,
        )
    text = out.getvalue()
    assert "calibration" in text
    assert "conf [" in text


# --------------------------------------------------------------------------- #
# Task 1 — predicted_confidence on ObservationReport; harness prefers it
# --------------------------------------------------------------------------- #


def test_predicted_confidence_field_accepted():
    """ObservationReport accepts an optional predicted_confidence in [0,1]."""
    r = ObservationReport(
        headline="h",
        bias="bullish",
        summary="s",
        next_check_in="tomorrow",
        predicted_confidence=0.73,
    )
    assert r.predicted_confidence == 0.73
    # Default is None (additive / backward-compatible)
    r2 = ObservationReport(headline="h", bias="bullish", summary="s", next_check_in="t")
    assert r2.predicted_confidence is None


def test_confidence_prefers_predicted_confidence_over_signal_mean():
    """When predicted_confidence is set, it wins over the signal-mean fallback."""
    r = _report("bullish", confs=(0.2, 0.4))  # signal mean would be 0.3
    r.predicted_confidence = 0.9
    assert _confidence_from_report(r) == 0.9


def test_confidence_falls_back_to_signal_mean_when_unset():
    """predicted_confidence=None -> mean of per-signal confidences (legacy behavior)."""
    r = _report("bullish", confs=(0.6, 1.0))  # mean 0.8
    assert r.predicted_confidence is None
    assert _confidence_from_report(r) == 0.8


def test_confidence_none_when_no_signals_and_no_predicted():
    r = ObservationReport(headline="h", bias="bullish", summary="s", next_check_in="t")
    assert _confidence_from_report(r) is None


# --------------------------------------------------------------------------- #
# Task 2 — EvalRun model + persist_eval_run helper
# --------------------------------------------------------------------------- #


def test_persist_eval_run_maps_result_to_row(db):
    result = {
        "label": "smoke",
        "model": "claude-sonnet-4-6",
        "horizon": 30,
        "n": 5,
        "skipped": 1,
        "scored": 4,
        "hit_rate": 0.75,
        "brier": 0.21,
        "avg_confidence": 0.68,
        "calibration_error": 0.12,
        "calibration": [
            {
                "bin_low": 0.7,
                "bin_high": 0.9,
                "n": 4,
                "hits": 3,
                "observed_hit_rate": 0.75,
                "mean_confidence": 0.68,
            }
        ],
        "examples": [{"predicted_direction": "bullish", "hit": True}],
    }
    from apps.aieval.models import EvalRun

    run = persist_eval_run(result, source="scheduled")
    assert isinstance(run, EvalRun)
    assert run.pk is not None
    assert run.source == "scheduled"
    assert run.label == "smoke"
    assert run.model == "claude-sonnet-4-6"
    assert run.horizon == 30
    assert run.n == 5 and run.skipped == 1 and run.scored == 4
    assert run.hit_rate == 0.75 and run.brier == 0.21
    assert run.avg_confidence == 0.68 and run.calibration_error == 0.12
    assert run.calibration[0]["observed_hit_rate"] == 0.75
    assert run.examples[0]["hit"] is True


def test_persist_eval_run_defaults_source_manual(db):
    run = persist_eval_run({"label": "x", "model": "m", "n": 0})
    assert run.source == "manual"
    assert run.horizon is None and run.hit_rate is None


# --------------------------------------------------------------------------- #
# Task 3 — read-only DRF views at /api/aieval/runs/
# --------------------------------------------------------------------------- #


def test_eval_runs_list_endpoint(db):
    persist_eval_run(
        {
            "label": "a",
            "model": "claude-sonnet-4-6",
            "n": 3,
            "scored": 3,
            "hit_rate": 0.66,
            "brier": 0.2,
        },
        source="manual",
    )
    persist_eval_run(
        {
            "label": "b",
            "model": "claude-opus-4-8",
            "n": 5,
            "scored": 5,
            "hit_rate": 0.8,
            "brier": 0.15,
        },
        source="scheduled",
    )
    resp = APIClient().get("/api/aieval/runs/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # newest first (ordering = -created_at); both labels present
    labels = {row["label"] for row in data}
    assert labels == {"a", "b"}
    assert "calibration" in data[0] and "hit_rate" in data[0]


def test_eval_runs_latest_endpoint(db):
    persist_eval_run({"label": "old", "model": "m", "n": 1}, source="manual")
    newest = persist_eval_run(
        {"label": "new", "model": "m", "n": 2, "hit_rate": 0.5}, source="scheduled"
    )
    resp = APIClient().get("/api/aieval/runs/latest/")
    assert resp.status_code == 200
    assert resp.json()["id"] == newest.id
    assert resp.json()["label"] == "new"


def test_eval_runs_latest_204_when_empty(db):
    resp = APIClient().get("/api/aieval/runs/latest/")
    assert resp.status_code == 204


# --------------------------------------------------------------------------- #
# Task 4 — cost-cap pre-flight + persist EvalRun on the manual command
# --------------------------------------------------------------------------- #


def _record_spend(provider="claude", cost="2.00"):
    """Record `cost` USD of provider spend 'today' via a real AIRun row.

    AIRun.message is a non-null OneToOneField, so build the minimal
    Thread -> Message -> AIRun chain. created_at is auto_now_add (counts as today).
    """
    from decimal import Decimal

    from apps.threads.models import AIRun, Message, Thread

    t = Thread.objects.create()
    m = Message.objects.create(thread=t, role="assistant")
    return AIRun.objects.create(
        message=m,
        provider=provider,
        model="claude-opus-4-8",
        status="done",
        cost_usd=Decimal(cost),
    )


def test_preflight_cost_cap_no_config_is_noop(db):
    from apps.aieval.services import preflight_cost_cap

    # No ProviderConfig row -> Infinity daily / None monthly -> never raises.
    preflight_cost_cap("claude")  # must not raise


def test_preflight_cost_cap_raises_when_over(db):
    from decimal import Decimal

    from apps.ai.cost import CostCapExceededError
    from apps.aieval.services import preflight_cost_cap
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    _record_spend("claude", "2.00")  # $2 spent today, cap is $1
    with pytest.raises(CostCapExceededError):
        preflight_cost_cap("claude")


def test_command_aborts_on_cost_cap(profile):
    from decimal import Decimal

    from django.core.management import CommandError

    from apps.secrets.models import ProviderConfig

    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    _record_spend("claude", "2.00")
    with pytest.raises(CommandError):
        call_command("aieval", "--model", "claude-opus-4-8")


def test_command_persists_eval_run(profile):
    from apps.aieval.models import EvalRun

    _postmortem(_thesis(profile, snapshot=_snapshot(profile)), verdict="correct", fwd=5.0)
    out = StringIO()
    with patch.object(svc, "run_structured", return_value=_report("bullish")):
        call_command(
            "aieval",
            "--model",
            "claude-opus-4-8",
            "--limit",
            "1",
            "--label",
            "persisted",
            stdout=out,
        )
    rows = EvalRun.objects.filter(label="persisted")
    assert rows.count() == 1
    assert rows.first().source == "manual"
