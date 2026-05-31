"""Live AI prediction calibration (M13 F3).

The AI's OWN track record, aggregated from resolved ``AIPrediction`` rows — the
third calibration source on the scorecard, alongside trader-thesis calibration
and offline eval calibration. The gap between the offline eval and this live
figure is diagnostic (distribution shift the frozen-replay harness can't see).

On-demand, no AI key, no scheduled task — like the other analytics. Population
mirrors the thesis scorecard: decisive-or-mixed predictions with a real forward
return (``inconclusive`` rows, which have a null forward return, are excluded).
Brier uses the model's **stated confidence** directly — cleaner than the thesis
conviction→prob map, because the AI states a probability.
"""

from __future__ import annotations

from datetime import datetime

_DECISIVE = ("correct", "incorrect")
_ALL_VERDICTS = ("correct", "incorrect", "mixed")
# Reliability-table confidence bands. The last band's upper edge is open (>1.0)
# so a stated confidence of exactly 1.0 lands in it.
_BANDS = ((0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


def _hit_rate(correct: int, incorrect: int) -> float | None:
    den = correct + incorrect
    return round(correct / den, 4) if den else None


def _band_label(lo: float, hi: float) -> str:
    return f"{lo:.1f}-{min(hi, 1.0):.1f}"


def _band_for(conf: float) -> str:
    for lo, hi in _BANDS:
        if lo <= conf < hi:
            return _band_label(lo, hi)
    return _band_label(*_BANDS[-1])


def _resolved_qs(start: datetime, end: datetime, horizon: int | None):
    from apps.predictions.models import AIPrediction

    qs = AIPrediction.objects.filter(
        status="resolved",
        resolved_at__gte=start,
        resolved_at__lt=end,
        forward_return_pct__isnull=False,
    )
    if horizon is not None:
        qs = qs.filter(horizon_days=horizon)
    return qs


def ai_calibration(*, start: datetime, end: datetime, horizon: int | None = None) -> dict:
    """Reliability by confidence band (Brier from stated confidence) + per
    (provider, model) and per direction hit-rates, over resolved predictions."""
    rows = list(
        _resolved_qs(start, end, horizon).values_list(
            "confidence", "direction", "verdict", "provider", "model"
        )
    )

    bands: dict[str, dict] = {}
    by_dir: dict[str, dict] = {}
    by_model: dict[tuple[str, str], dict] = {}
    tot = {"scored": 0, "correct": 0, "incorrect": 0, "mixed": 0}
    brier_terms: list[float] = []

    for conf, direction, verdict, provider, model in rows:
        tot["scored"] += 1
        if verdict in _ALL_VERDICTS:
            tot[verdict] += 1

        bl = _band_for(conf)
        b = bands.setdefault(
            bl, {"band": bl, "n": 0, "correct": 0, "incorrect": 0, "conf_sum": 0.0}
        )
        b["n"] += 1
        b["conf_sum"] += conf
        if verdict in _DECISIVE:
            b[verdict] += 1
            outcome = 1.0 if verdict == "correct" else 0.0
            brier_terms.append((conf - outcome) ** 2)

        d = by_dir.setdefault(direction, {"n": 0, "correct": 0, "incorrect": 0})
        d["n"] += 1
        if verdict in _DECISIVE:
            d[verdict] += 1

        m = by_model.setdefault(
            (provider, model),
            {"provider": provider, "model": model, "n": 0, "correct": 0, "incorrect": 0},
        )
        m["n"] += 1
        if verdict in _DECISIVE:
            m[verdict] += 1

    reliability = []
    for lo, hi in _BANDS:
        b = bands.get(_band_label(lo, hi))
        if not b:
            continue
        reliability.append(
            {
                "band": b["band"],
                "n": b["n"],
                "correct": b["correct"],
                "incorrect": b["incorrect"],
                "mean_confidence": round(b["conf_sum"] / b["n"], 4),
                "observed_hit_rate": _hit_rate(b["correct"], b["incorrect"]),
            }
        )

    model_rows = sorted(by_model.values(), key=lambda r: r["n"], reverse=True)
    for m in model_rows:
        m["hit_rate"] = _hit_rate(m["correct"], m["incorrect"])

    return {
        "horizon": horizon,
        "overall": {
            "scored": tot["scored"],
            "hit_rate": _hit_rate(tot["correct"], tot["incorrect"]),
            "correct": tot["correct"],
            "incorrect": tot["incorrect"],
            "mixed": tot["mixed"],
        },
        "brier": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
        "reliability": reliability,
        "by_provider_model": model_rows,
        "by_direction": {
            d: {"n": v["n"], "hit_rate": _hit_rate(v["correct"], v["incorrect"])}
            for d, v in by_dir.items()
        },
    }


def ai_calibration_drilldown(
    *,
    start: datetime,
    end: datetime,
    horizon: int | None = None,
    band: str | None = None,
    direction: str | None = None,
    verdict: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict:
    """The resolved predictions behind a band/slice. Same population as
    ``ai_calibration`` narrowed by the filters, so counts reconcile with the
    aggregate's bucket ``n``."""
    qs = _resolved_qs(start, end, horizon)
    if direction:
        qs = qs.filter(direction=direction)
    if verdict:
        qs = qs.filter(verdict=verdict)
    if provider:
        qs = qs.filter(provider=provider)
    if model:
        qs = qs.filter(model=model)

    rows = []
    for p in qs.order_by("-resolved_at"):
        if band is not None and _band_for(p.confidence) != band:
            continue
        rows.append(
            {
                "id": p.id,
                "ticker": p.ticker,
                "direction": p.direction,
                "horizon_days": p.horizon_days,
                "confidence": round(p.confidence, 4),
                "verdict": p.verdict,
                "forward_return_pct": p.forward_return_pct,
                "provider": p.provider,
                "model": p.model,
                "predicted_at": p.predicted_at.isoformat(),
                "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
            }
        )
    return {
        "horizon": horizon,
        "count": len(rows),
        "filters": {
            "band": band,
            "direction": direction,
            "verdict": verdict,
            "provider": provider,
            "model": model,
        },
        "rows": rows,
    }
