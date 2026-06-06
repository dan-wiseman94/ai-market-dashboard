"""Calibration scorecard: thesis conviction-vs-outcome + provider hit-rate.

On-demand aggregation over PostMortem ⋈ Thesis (and Thesis → source thread →
AIRun.provider). No AI key, no scheduled task — like the other analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

VALID_HORIZONS = (7, 30, 90)
_DECISIVE = ("correct", "incorrect")
_ALL_VERDICTS = ("correct", "incorrect", "mixed", "inconclusive")


def _prob_for_conviction(conviction: int) -> float:
    """Linear map conviction 1..5 -> implied probability 0.5..0.9 (documented, returned in payload)."""
    c = max(1, min(5, int(conviction)))
    return round(0.5 + (c - 1) / 4 * 0.4, 4)


PROB_MAP = {c: _prob_for_conviction(c) for c in range(1, 6)}


def _hit_rate(correct: int, incorrect: int) -> float | None:
    den = correct + incorrect
    return round(correct / den, 4) if den else None


def _thesis_section(rows: list[tuple[int, str, str, float | None]]) -> dict:
    buckets: dict[int, dict[str, Any]] = {
        c: {
            "conviction": c,
            "n": 0,
            "correct": 0,
            "incorrect": 0,
            "mixed": 0,
            "inconclusive": 0,
            "hit_rate": None,
        }
        for c in range(1, 6)
    }
    by_dir: dict[str, dict] = {}
    tot = {"scored": 0, "correct": 0, "incorrect": 0, "mixed": 0, "inconclusive": 0}
    brier_terms: list[float] = []
    ret_sum, ret_n = 0.0, 0

    for conviction, direction, verdict, fwd in rows:
        c = max(1, min(5, int(conviction)))
        b = buckets[c]
        b["n"] += 1
        tot["scored"] += 1
        if verdict in _ALL_VERDICTS:
            b[verdict] += 1
            tot[verdict] += 1
        d = by_dir.setdefault(direction, {"n": 0, "correct": 0, "incorrect": 0})
        d["n"] += 1
        if verdict in _DECISIVE:
            d[verdict] += 1
            o = 1.0 if verdict == "correct" else 0.0
            brier_terms.append((_prob_for_conviction(c) - o) ** 2)
        if fwd is not None:
            ret_sum += float(fwd)
            ret_n += 1

    for b in buckets.values():
        b["hit_rate"] = _hit_rate(b["correct"], b["incorrect"])

    return {
        "buckets": [buckets[c] for c in range(1, 6)],
        "brier": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
        "prob_map": PROB_MAP,
        "overall": {
            "scored": tot["scored"],
            "hit_rate": _hit_rate(tot["correct"], tot["incorrect"]),
            "correct": tot["correct"],
            "incorrect": tot["incorrect"],
            "mixed": tot["mixed"],
            "inconclusive": tot["inconclusive"],
            "avg_forward_return_pct": round(ret_sum / ret_n, 4) if ret_n else None,
        },
        "by_direction": {
            d: {"n": v["n"], "hit_rate": _hit_rate(v["correct"], v["incorrect"])}
            for d, v in by_dir.items()
        },
    }


def _provider_section(pms) -> tuple[list[dict], int]:
    from apps.threads.models import AIRun

    agg: dict[tuple[str, str], dict] = {}
    attributable = 0
    for pm in pms:
        thread_id = pm.thesis.thread_id
        if not thread_id:
            continue
        pairs = list(
            AIRun.objects.filter(message__thread_id=thread_id, status="done")
            .values_list("provider", "model")
            .distinct()
        )
        if not pairs:
            continue
        attributable += 1
        for provider, model in pairs:
            a = agg.setdefault(
                (provider, model),
                {"provider": provider, "model": model, "n": 0, "correct": 0, "incorrect": 0},
            )
            a["n"] += 1
            if pm.verdict in _DECISIVE:
                a[pm.verdict] += 1
    rows = []
    for a in agg.values():
        a["hit_rate"] = _hit_rate(a["correct"], a["incorrect"])
        rows.append(a)
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows, attributable


def track_record_for_ticker(
    ticker: str, *, direction: str | None = None, conviction: int | None = None, min_n: int = 3
) -> dict | None:
    """Deterministic (no-AI) track record for one ticker, plus an optional
    direction+conviction slice over all history.

    Per-ticker summary uses closed `Thesis.status` (what actually happened to
    your calls on this name). The slice uses decisive `PostMortem` verdicts for
    theses matching direction+conviction (objective forward-return outcome).
    Returns None when there is not enough history to be meaningful (ticker
    closed-count < min_n AND no qualifying slice of >= min_n).
    """
    from apps.thesis.models import PostMortem, Thesis

    ticker = (ticker or "").upper()
    if not ticker:
        return None

    counts = {"win": 0, "loss": 0, "scratch": 0, "invalidated": 0}
    _by_status = {
        "closed_win": "win",
        "closed_loss": "loss",
        "closed_scratch": "scratch",
        "invalidated": "invalidated",
    }
    last = None
    for t in Thesis.objects.filter(ticker=ticker).exclude(status="open").order_by("-opened_at"):
        key = _by_status.get(t.status)
        if key:
            counts[key] += 1
        if last is None:
            last = {"direction": t.direction, "conviction": t.conviction, "status": t.status}
    ticker_n = sum(counts.values())

    slice_info = None
    if direction is not None and conviction is not None:
        pms = PostMortem.objects.filter(
            status="done",
            verdict__in=_DECISIVE,
            thesis__direction=direction,
            thesis__conviction=conviction,
        )
        n = pms.count()
        if n >= min_n:
            correct = sum(1 for v in pms.values_list("verdict", flat=True) if v == "correct")
            slice_info = {
                "direction": direction,
                "conviction": conviction,
                "correct": correct,
                "n": n,
                "hit_rate": _hit_rate(correct, n - correct),
            }

    if ticker_n < min_n and slice_info is None:
        return None
    return {
        "ticker": ticker,
        "closed_n": ticker_n,
        "counts": counts,
        "hit_rate": _hit_rate(counts["win"], counts["loss"]),
        "last": last,
        "slice": slice_info,
    }


def calibration(*, start: datetime, end: datetime, horizon: int = 30) -> dict:
    from apps.thesis.models import PostMortem

    horizon = horizon if horizon in VALID_HORIZONS else 30
    pms = list(
        PostMortem.objects.filter(
            status="done",
            horizon_days=horizon,
            completed_at__gte=start,
            completed_at__lt=end,
            forward_return_pct__isnull=False,
        ).select_related("thesis")
    )
    thesis_rows = [
        (pm.thesis.conviction, pm.thesis.direction, pm.verdict, pm.forward_return_pct) for pm in pms
    ]
    thesis = _thesis_section(thesis_rows)
    provider, attributable = _provider_section(pms)
    return {
        "horizon": horizon,
        "scored": thesis["overall"]["scored"],
        "attributable": attributable,
        "thesis": thesis,
        "provider": provider,
    }


def calibration_drilldown(
    *,
    start: datetime,
    end: datetime,
    horizon: int = 30,
    conviction: int | None = None,
    direction: str | None = None,
    verdict: str | None = None,
) -> dict:
    """The underlying theses behind a calibration bucket (scorecard drill-down).

    Same PostMortem ⋈ Thesis population that builds the buckets in `calibration`
    (decisive-or-mixed, non-null forward return, in window + horizon), narrowed
    to one bucket by any of conviction / direction / verdict. Counts therefore
    reconcile with the aggregate scorecard's bucket `n`. Returns flat, JSON-ready
    rows ordered newest-first.
    """
    from apps.thesis.models import PostMortem

    horizon = horizon if horizon in VALID_HORIZONS else 30
    qs = (
        PostMortem.objects.filter(
            status="done",
            horizon_days=horizon,
            completed_at__gte=start,
            completed_at__lt=end,
            forward_return_pct__isnull=False,
        )
        .select_related("thesis")
        .order_by("-completed_at")
    )
    if conviction is not None:
        qs = qs.filter(thesis__conviction=conviction)
    if direction is not None:
        qs = qs.filter(thesis__direction=direction)
    if verdict is not None:
        qs = qs.filter(verdict=verdict)

    rows = [
        {
            "thesis_id": pm.thesis_id,
            "title": pm.thesis.title,
            "ticker": pm.thesis.ticker,
            "direction": pm.thesis.direction,
            "conviction": pm.thesis.conviction,
            "verdict": pm.verdict,
            "forward_return_pct": pm.forward_return_pct,
            "horizon_days": pm.horizon_days,
            "completed_at": pm.completed_at.isoformat() if pm.completed_at else None,
            "thread_id": pm.thesis.thread_id,
        }
        for pm in qs
    ]
    return {
        "horizon": horizon,
        "count": len(rows),
        "filters": {"conviction": conviction, "direction": direction, "verdict": verdict},
        "rows": rows,
    }
