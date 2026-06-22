"""Calibration-drift detection (#14).

Trend ``EvalRun.calibration_error`` per model and flag a model that has drifted
from well-calibrated to over/under-confident. Pure read; honest about thin data
(``insufficient_history`` rather than a verdict on too few runs).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

_DRIFT_ABS = 0.05  # recent error must worsen by ≥ this absolute amount …
_DRIFT_REL = 1.5  # … AND by ≥ 50% relative, to avoid noise
_DIR_BAND = 0.05  # confidence-vs-hit-rate gap that counts as over/under-confident


def _mean(vals: list) -> float | None:
    nums = [v for v in vals if v is not None]
    return round(sum(nums) / len(nums), 4) if nums else None


def _direction(latest: dict | None) -> str:
    """over/under-confident from the most-recent run's avg_confidence vs hit_rate."""
    if not latest:
        return "stable"
    conf, hit = latest.get("avg_confidence"), latest.get("hit_rate")
    if conf is None or hit is None:
        return "stable"
    gap = conf - hit
    if gap > _DIR_BAND:
        return "overconfident"
    if gap < -_DIR_BAND:
        return "underconfident"
    return "stable"


def calibration_drift(
    *, window_days: int = 30, min_runs: int = 3, now: datetime | None = None
) -> dict:
    """Per-model drift of calibration_error: recent window vs the prior window."""
    from apps.analytics.models import EvalRun

    now = now or timezone.now()
    recent_start = now - timedelta(days=window_days)
    baseline_start = now - timedelta(days=2 * window_days)

    rows = list(
        EvalRun.objects.filter(created_at__gte=baseline_start, scored__gt=0)
        .values("model", "created_at", "calibration_error", "hit_rate", "avg_confidence")
        .order_by("model", "-created_at")
    )

    by_model: dict[str, dict] = {}
    for r in rows:
        bucket = by_model.setdefault(r["model"], {"recent": [], "baseline": [], "latest": None})
        if r["created_at"] >= recent_start:
            bucket["recent"].append(r)
            if bucket["latest"] is None:
                bucket["latest"] = r  # rows are -created_at, so first recent is newest
        else:
            bucket["baseline"].append(r)

    models = []
    for model, b in sorted(by_model.items()):
        recent_err = _mean([x["calibration_error"] for x in b["recent"]])
        base_err = _mean([x["calibration_error"] for x in b["baseline"]])
        if len(b["recent"]) < min_runs or len(b["baseline"]) < min_runs:
            models.append(
                {
                    "model": model,
                    "recent_error": recent_err,
                    "baseline_error": base_err,
                    "delta": None,
                    "drifting": False,
                    "direction": "stable",
                    "status": "insufficient_history",
                    "recent_runs": len(b["recent"]),
                    "baseline_runs": len(b["baseline"]),
                }
            )
            continue
        delta = (
            round(recent_err - base_err, 4)
            if recent_err is not None and base_err is not None
            else None
        )
        drifting = bool(
            recent_err is not None
            and base_err is not None
            and delta is not None
            and delta >= _DRIFT_ABS
            and recent_err >= base_err * _DRIFT_REL
        )
        models.append(
            {
                "model": model,
                "recent_error": recent_err,
                "baseline_error": base_err,
                "delta": delta,
                "drifting": drifting,
                "direction": _direction(b["latest"]),
                "status": "scored",
                "recent_runs": len(b["recent"]),
                "baseline_runs": len(b["baseline"]),
            }
        )

    return {"generated_at": now.isoformat(), "window_days": window_days, "models": models}
