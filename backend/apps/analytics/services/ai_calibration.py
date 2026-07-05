"""Live AI prediction calibration.

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

# Share the decisive-verdict set and hit-rate helper with the thesis scorecard
# (same package) — aieval already imports _hit_rate from here too.
from apps.analytics.services.calibration import _DECISIVE, _hit_rate

_ALL_VERDICTS = ("correct", "incorrect", "mixed")
# Reliability-table confidence bands. The last band's upper edge is open (>1.0)
# so a stated confidence of exactly 1.0 lands in it.
_BANDS = ((0.0, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


def _band_label(lo: float, hi: float) -> str:
    return f"{lo:.1f}-{min(hi, 1.0):.1f}"


def _band_for(conf: float) -> str:
    for lo, hi in _BANDS:
        if lo <= conf < hi:
            return _band_label(lo, hi)
    return _band_label(*_BANDS[-1])


def _resolved_qs(start: datetime, end: datetime, horizon: int | None):
    from apps.observer.models import AIPrediction

    qs = AIPrediction.objects.filter(
        status="resolved",
        resolved_at__gte=start,
        resolved_at__lt=end,
        forward_return_pct__isnull=False,
    )
    if horizon is not None:
        qs = qs.filter(horizon_days=horizon)
    return qs


def _bump(store: dict, key, verdict: str, extra: dict | None = None) -> dict:
    """Accumulate one scored row into a ``{n, correct, incorrect, …}`` bucket,
    counting the decisive verdict. Returns the bucket for any extra in-place work."""
    row = store.setdefault(key, {"n": 0, "correct": 0, "incorrect": 0, **(extra or {})})
    row["n"] += 1
    if verdict in _DECISIVE:
        row[verdict] += 1
    return row


def ai_calibration(*, start: datetime, end: datetime, horizon: int | None = None) -> dict:
    """Reliability by confidence band (Brier from stated confidence) + per
    (provider, model) and per direction hit-rates, over resolved predictions."""
    rows = list(
        _resolved_qs(start, end, horizon).values_list(
            "confidence",
            "direction",
            "verdict",
            "provider",
            "model",
            "expected_move_pct",
            "forward_return_pct",
        )
    )

    bands: dict[str, dict] = {}
    by_dir: dict[str, dict] = {}
    by_model: dict[tuple[str, str], dict] = {}
    tot = {"scored": 0, "correct": 0, "incorrect": 0, "mixed": 0}
    brier_terms: list[float] = []
    # Beat-the-straddle: did the actual move exceed the options-priced 1σ move?
    # expected_move_pct is a FRACTION; forward_return_pct is a PERCENT → compare |fwd| > priced*100.
    straddle = {"n": 0, "beyond": 0, "edge": 0}

    for conf, direction, verdict, provider, model, exp_move, fwd in rows:
        tot["scored"] += 1
        if verdict in _ALL_VERDICTS:
            tot[verdict] += 1

        bl = _band_for(conf)
        band = _bump(bands, bl, verdict, {"band": bl, "conf_sum": 0.0})
        band["conf_sum"] += conf
        if verdict in _DECISIVE:
            brier_terms.append((conf - (1.0 if verdict == "correct" else 0.0)) ** 2)

        _bump(by_dir, direction, verdict)
        _bump(by_model, (provider, model), verdict, {"provider": provider, "model": model})

        if exp_move and exp_move > 0 and fwd is not None:
            straddle["n"] += 1
            if abs(fwd) > exp_move * 100.0:
                straddle["beyond"] += 1
                if verdict == "correct":
                    straddle["edge"] += 1

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
        "beat_the_straddle": {
            "n": straddle["n"],
            "beyond_priced": straddle["beyond"],
            "within_priced": straddle["n"] - straddle["beyond"],
            # share of priced predictions whose actual move exceeded the options-implied move
            "beyond_rate": round(straddle["beyond"] / straddle["n"], 4) if straddle["n"] else None,
            # the strongest cell: directionally CORRECT and bigger than priced
            "edge_rate": round(straddle["edge"] / straddle["n"], 4) if straddle["n"] else None,
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
