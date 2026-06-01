from __future__ import annotations

import logging

from apps.regime.models import RegimeReading
from apps.regime.services.classify import (
    build_drivers,
    classify_breadth,
    classify_leadership,
    classify_rates,
    classify_trend,
    classify_volatility,
    fold_composite,
)
from apps.regime.services.inputs import gather_inputs
from apps.regime.services.narrative import regime_narrative

log = logging.getLogger(__name__)


def current_regime() -> RegimeReading | None:
    """The latest reading, or None when no reading has been produced yet."""
    return RegimeReading.objects.order_by("-created_at").first()


def _classify(inp: dict) -> dict[str, str]:
    return {
        "volatility": classify_volatility(inp.get("vix_last"), inp.get("vix_percentile")),
        "trend": classify_trend(inp.get("spx_ma_spread"), inp.get("spx_dist_50")),
        "breadth": classify_breadth(inp.get("breadth") or {}),
        "leadership": classify_leadership(inp.get("sector_returns") or {}),
        "rates": classify_rates(inp.get("t10y2y"), inp.get("tnx_change")),
    }


def changed_axes(prior: RegimeReading, axes: dict[str, str]) -> list[str]:
    prior_axes = prior.axes or {}
    return [k for k, v in axes.items() if prior_axes.get(k) != v]


def _notify_change(prior: RegimeReading, reading: RegimeReading) -> None:
    from apps.observer.services.notifications import notify

    notify(
        user_id=None,
        kind="regime",
        title=f"Regime change: {prior.composite} → {reading.composite}",
        body="; ".join(reading.drivers[:3]),
        link="/regime",
        meta={"reading_id": reading.id, "prior": prior.composite, "current": reading.composite},
    )


def compute_and_store() -> RegimeReading:
    """Gather -> classify -> persist -> alert on composite change. Never raises out
    of the deterministic core (narrative is already best-effort)."""
    inp = gather_inputs()
    axes = _classify(inp)
    composite = fold_composite(axes)
    drivers = build_drivers(axes, inp)

    prior = current_regime()
    changed = changed_axes(prior, axes) if prior else []
    narrative = regime_narrative(composite, axes, drivers)  # best-effort, "" on failure

    reading = RegimeReading.objects.create(
        composite=composite,
        axes=axes,
        drivers=drivers,
        inputs=inp,
        narrative=narrative,
        changed_axes=changed,
    )
    if prior is not None and prior.composite != reading.composite:
        try:
            _notify_change(prior, reading)
        except Exception:
            log.warning("regime.notify_failed", exc_info=True)
    return reading
