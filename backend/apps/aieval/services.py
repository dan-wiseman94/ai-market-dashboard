"""Offline AI evaluation harness — replay a candidate (system_prompt, model)
against the FROZEN source snapshots of past theses whose outcome we already know.

LOOK-AHEAD SAFETY (the core hazard / core invariant)
-----------------------------------------------------
Each labeled example is a ``Thesis`` that has BOTH a frozen source ``snapshot``
(the market state at thesis-open) AND a decisive ``PostMortem`` (the objective
outcome we learned later). To score a candidate fairly we re-run it against ONLY
what was knowable at ``thesis.opened_at``: the bare serialized snapshot.

We therefore call ``serialize_for_ai(snapshot, ...)`` and pass its output
straight to the model. We DELIBERATELY do NOT call
``apps.threads.coach.assemble_coach_context`` (or recall, or any post-trade
context) — the coach block summarizes prior outcomes and could leak information
from AFTER the thesis was opened, which would inflate the score. Snapshot
sections are immutable post-capture, so re-serializing reproduces the original
input exactly. Keep this boundary: the user turn handed to ``run_structured``
must contain only the snapshot.

This module is pure + testable. ``run_structured`` is the only side-effecting
call (the real model → real $). Tests patch it; the management command guards it
behind cost caps + a manual trigger + ``--limit``.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.ai.providers.claude_structured import run_structured
from apps.aieval.models import EvalRun
from apps.analytics.services.calibration import _hit_rate, _prob_for_conviction
from apps.observer.schemas import ObservationReport
from apps.snapshots.serializer import serialize_for_ai
from apps.thesis.models import PostMortem

log = logging.getLogger(__name__)

_DECISIVE = ("correct", "incorrect")
# Direction opposite, used to recover the OUTCOME direction from (thesis dir, verdict).
_OPPOSITE = {"bullish": "bearish", "bearish": "bullish", "neutral": "neutral"}

# Reliability bins for stated-confidence calibration.
_CONF_BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]


def confidence_calibration(results: list[dict]) -> list[dict]:
    """Reliability curve: bucket scored predictions by stated confidence, report observed hit-rate.

    Only includes predictions with a non-None confidence AND a non-None hit (decisive, scored).
    Each bucket: {bin_low, bin_high, n, hits, observed_hit_rate (float|None), mean_confidence (float|None)}.
    A well-calibrated model has observed_hit_rate ≈ mean_confidence within each bucket.
    """
    buckets = []
    for lo, hi in _CONF_BINS:
        rows = [
            r
            for r in results
            if r.get("confidence") is not None
            and r.get("hit") is not None
            and lo <= r["confidence"] < hi
        ]
        n = len(rows)
        hits = sum(1 for r in rows if r["hit"])
        confs = [r["confidence"] for r in rows]
        buckets.append(
            {
                "bin_low": lo,
                "bin_high": min(hi, 1.0),
                "n": n,
                "hits": hits,
                "observed_hit_rate": round(hits / n, 4) if n else None,
                "mean_confidence": round(sum(confs) / len(confs), 4) if confs else None,
            }
        )
    return buckets


def labeled_examples(*, horizon: int | None = None, limit: int | None = None) -> list[PostMortem]:
    """Decisive ``PostMortem`` ⋈ ``Thesis`` rows that have a frozen source
    snapshot + a known objective outcome.

    A row qualifies only when the post-mortem is decisive (``status='done'``,
    verdict in correct/incorrect, ``forward_return_pct`` not null) AND the thesis
    has a ``snapshot`` FK (the frozen input we can replay). ``horizon`` filters
    ``horizon_days``; ``limit`` caps the number replayed (cheap smoke runs).
    """
    qs = (
        PostMortem.objects.filter(
            status="done",
            verdict__in=_DECISIVE,
            forward_return_pct__isnull=False,
            thesis__snapshot__isnull=False,
        )
        .select_related("thesis", "thesis__snapshot")
        .order_by("id")
    )
    if horizon is not None:
        qs = qs.filter(horizon_days=horizon)
    if limit is not None:
        return list(qs[:limit])
    return list(qs)


def _direction_from_report(report: ObservationReport) -> str | None:
    """Map the model's call to a thesis direction, or None if not directional.

    ``bias`` is the top-level call. ``mixed`` is not a directional thesis call,
    so it scores as None (excluded from hit-rate/Brier) rather than being forced.
    """
    bias = getattr(report, "bias", None)
    if bias in ("bullish", "bearish", "neutral"):
        return bias
    return None  # "mixed" or anything unexpected


def _confidence_from_report(report: ObservationReport) -> float | None:
    """Stated confidence: the report's own predicted_confidence when set,
    else the mean of the per-signal confidences (legacy fallback)."""
    pc = getattr(report, "predicted_confidence", None)
    if pc is not None:
        return round(float(pc), 4)
    confs = [
        s.confidence
        for s in getattr(report, "signals", [])
        if getattr(s, "confidence", None) is not None
    ]
    if not confs:
        return None
    return round(sum(confs) / len(confs), 4)


def _outcome_direction(thesis_direction: str, verdict: str) -> str:
    """The direction that ACTUALLY played out, recovered from the thesis call +
    its objective verdict. If the thesis was 'correct', the market moved the way
    the thesis said; if 'incorrect', it moved the opposite way."""
    if verdict == "correct":
        return thesis_direction
    return _OPPOSITE.get(thesis_direction, thesis_direction)


def replay_one(example: PostMortem, *, system: str, model: str) -> dict[str, Any]:
    """Re-serialize the frozen snapshot, run the candidate, extract the call.

    Look-ahead-safe: the user turn is the BARE serialized snapshot — no coach,
    no recall, no post-trade context (see module docstring). Returns
    ``{predicted_direction, confidence, actual_verdict, thesis_direction,
    outcome_direction, hit}``. ``hit`` is None when the model gave no directional
    call (e.g. 'mixed'), so it is excluded from hit-rate/Brier upstream.
    """
    from apps.secrets.models import ProviderConfig

    thesis = example.thesis
    snapshot = thesis.snapshot

    # ONLY the frozen snapshot — deliberately no coach/recall context.
    payload_text = serialize_for_ai(snapshot, provider="claude", model=model)

    cfg = ProviderConfig.objects.filter(provider="claude").first()
    api_key = cfg.api_key if cfg else ""
    base_url = (cfg.base_url if cfg else "") or ""

    report = run_structured(
        api_key=api_key,
        model=model,
        system=system,
        user=payload_text,
        output_model=ObservationReport,
        base_url=base_url,
    )

    predicted = _direction_from_report(report)
    confidence = _confidence_from_report(report)
    outcome = _outcome_direction(thesis.direction, example.verdict)
    hit: bool | None = None if predicted is None else (predicted == outcome)

    return {
        "predicted_direction": predicted,
        "confidence": confidence,
        "actual_verdict": example.verdict,
        "thesis_direction": thesis.direction,
        "outcome_direction": outcome,
        "hit": hit,
    }


def evaluate(
    *,
    system: str,
    model: str,
    label: str,
    horizon: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Replay every labeled example through the candidate and aggregate.

    Scoring:
      - ``hit_rate`` = correct directional calls / decisive directional calls,
        where a call is 'correct' when the model's predicted direction matches
        the direction the market ACTUALLY took (recovered from the post-mortem
        verdict). Calls with no direction ('mixed') are excluded.
      - ``brier`` = mean over the same scored calls of ``(p - o)^2`` where
        ``p = _prob_for_conviction(thesis.conviction)`` (the documented
        conviction→prob map shared with the calibration scorecard) and
        ``o = 1.0`` if the call hit else ``0.0``.
      - ``avg_confidence`` = mean of the model's stated per-run confidences.

    NEVER raises: a row whose snapshot won't serialize or whose run errors is
    counted in ``skipped`` and dropped.
    """
    examples = labeled_examples(horizon=horizon, limit=limit)

    rows: list[dict[str, Any]] = []
    skipped = 0
    correct = 0
    incorrect = 0
    brier_terms: list[float] = []
    confidences: list[float] = []

    for ex in examples:
        # Broad except is intentional: evaluate must NEVER raise — a row whose
        # snapshot won't serialize or whose model run errors is counted as skipped.
        try:
            r = replay_one(ex, system=system, model=model)
        except Exception as exc:
            log.warning("aieval: skipping post-mortem %s — replay failed: %s", ex.id, exc)
            skipped += 1
            continue

        rows.append(r)
        if r["confidence"] is not None:
            confidences.append(r["confidence"])

        hit = r["hit"]
        if hit is None:
            continue  # non-directional call: not scored
        if hit:
            correct += 1
            o = 1.0
        else:
            incorrect += 1
            o = 0.0
        p = _prob_for_conviction(ex.thesis.conviction)
        brier_terms.append((p - o) ** 2)

    calibration = confidence_calibration(rows)
    non_empty = [b for b in calibration if b["n"] > 0]
    calibration_error: float | None = None
    if non_empty:
        abs_errors = [
            abs(b["observed_hit_rate"] - b["mean_confidence"])
            for b in non_empty
            if b["observed_hit_rate"] is not None and b["mean_confidence"] is not None
        ]
        calibration_error = round(sum(abs_errors) / len(abs_errors), 4) if abs_errors else None

    return {
        "label": label,
        "model": model,
        "horizon": horizon,
        "n": len(rows),
        "skipped": skipped,
        "scored": correct + incorrect,
        "hit_rate": _hit_rate(correct, incorrect),
        "brier": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
        "avg_confidence": (round(sum(confidences) / len(confidences), 4) if confidences else None),
        "examples": rows,
        "calibration": calibration,
        "calibration_error": calibration_error,
    }


def persist_eval_run(result: dict[str, Any], *, source: str = "manual") -> EvalRun:
    """Map an `evaluate()` result dict onto a stored `EvalRun` row.

    `source` is 'manual' (the management command) or 'scheduled' (the beat task).
    Tolerant of partial dicts (uses .get with sensible defaults) so a caller
    never has to assemble a full result to persist a smoke run.
    """
    return EvalRun.objects.create(
        source=source,
        label=result.get("label", "baseline"),
        model=result.get("model", ""),
        horizon=result.get("horizon"),
        n=result.get("n", 0),
        skipped=result.get("skipped", 0),
        scored=result.get("scored", 0),
        hit_rate=result.get("hit_rate"),
        brier=result.get("brier"),
        avg_confidence=result.get("avg_confidence"),
        calibration_error=result.get("calibration_error"),
        calibration=result.get("calibration", []),
        examples=result.get("examples", []),
    )
