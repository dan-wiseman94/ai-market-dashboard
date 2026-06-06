"""Trader calibration (M14 F4, "The Mirror"): turn the calibration apparatus on the
TRADER's own behavior, using decision-journal + thesis + post-mortem data the
product otherwise never reads. On-demand, indexed-column aggregation, ZERO new
models. Look-ahead-safe — reads decisive, completed post-mortems only.

Two signals (v1):
- decision_outcomes: how each journal decision (acted/passed/watching/hedged)
  correlates with the underlying thesis's realized verdict — e.g. "you PASSED on
  theses that resolved correct 7/9 times" = passing on winners.
- conviction_reliability: is the trader's conviction predictive, flat, or INVERTED
  (high-conviction calls resolving worse than low-conviction ones)?

(AI-vs-you divergence — where you overrode the AI and lost — is a v2 follow-on; it
needs the sparse thesis↔thread↔AIPrediction join.)
"""

from __future__ import annotations

_MIN_N = 4  # below this, a behavioral claim is a horoscope, not a finding


def trader_calibration(*, horizon_days: int = 30) -> dict:
    verdict_by_thesis = _decisive_verdicts(horizon_days)
    return {
        "horizon_days": horizon_days,
        "decision_outcomes": _decision_outcomes(verdict_by_thesis),
        "conviction_reliability": _conviction_reliability(horizon_days),
    }


def _decisive_verdicts(horizon_days: int) -> dict[int, str]:
    """thesis_id -> verdict for decisive post-mortems at the horizon (one per thesis,
    via the (thesis, horizon) unique constraint)."""
    from apps.thesis.models import PostMortem

    return dict(
        PostMortem.objects.filter(
            horizon_days=horizon_days, status="done", verdict__in=["correct", "incorrect"]
        ).values_list("thesis_id", "verdict")
    )


def _decision_outcomes(verdict_by_thesis: dict[int, str]) -> dict:
    from apps.thesis.models import DecisionJournalEntry

    if not verdict_by_thesis:
        return {"status": "insufficient_history", "buckets": []}
    entries = DecisionJournalEntry.objects.filter(
        thesis_id__in=verdict_by_thesis.keys()
    ).values_list("decision", "thesis_id")
    agg: dict[str, dict] = {}
    for decision, thesis_id in entries:
        verdict = verdict_by_thesis.get(thesis_id)
        if verdict is None:
            continue
        bucket = agg.setdefault(decision, {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += 1 if verdict == "correct" else 0
    buckets = [
        {
            "decision": decision,
            "n": bucket["n"],
            "correct": bucket["correct"],
            "hit_rate": round(bucket["correct"] / bucket["n"], 4),
        }
        for decision, bucket in sorted(agg.items())
        if bucket["n"] >= _MIN_N
    ]
    return {"status": "ok" if buckets else "insufficient_history", "buckets": buckets}


def _conviction_reliability(horizon_days: int) -> dict:
    from apps.thesis.models import PostMortem

    rows = PostMortem.objects.filter(
        horizon_days=horizon_days, status="done", verdict__in=["correct", "incorrect"]
    ).values_list("thesis__conviction", "verdict")
    by_conviction: dict[int, dict] = {}
    for conviction, verdict in rows:
        if conviction is None:
            continue
        bucket = by_conviction.setdefault(int(conviction), {"n": 0, "correct": 0})
        bucket["n"] += 1
        bucket["correct"] += 1 if verdict == "correct" else 0
    buckets = [
        {
            "conviction": conviction,
            "n": bucket["n"],
            "correct": bucket["correct"],
            "hit_rate": round(bucket["correct"] / bucket["n"], 4),
        }
        for conviction, bucket in sorted(by_conviction.items())
    ]
    overall_verdict = _conviction_verdict(by_conviction)
    has_signal = any(b["n"] >= _MIN_N for b in buckets)
    return {
        "status": "ok" if has_signal else "insufficient_history",
        "buckets": buckets,
        "verdict": overall_verdict,
    }


def _conviction_verdict(by_conviction: dict[int, dict]) -> str | None:
    """'inverted' | 'flat' | 'aligned' from high (>=4) vs low (<=2) conviction
    hit-rates, or None when either pool is below the min-n floor."""
    high = _pool(by_conviction, lambda c: c >= 4)
    low = _pool(by_conviction, lambda c: c <= 2)
    if not high or not low or high["n"] < _MIN_N or low["n"] < _MIN_N:
        return None
    delta = (high["correct"] / high["n"]) - (low["correct"] / low["n"])
    if delta <= -0.10:
        return "inverted"  # your "sure things" resolve WORSE than your hedged calls
    if delta >= 0.10:
        return "aligned"
    return "flat"


def _pool(by_conviction: dict[int, dict], predicate) -> dict | None:
    n = correct = 0
    for conviction, bucket in by_conviction.items():
        if predicate(conviction):
            n += bucket["n"]
            correct += bucket["correct"]
    return {"n": n, "correct": correct} if n else None
