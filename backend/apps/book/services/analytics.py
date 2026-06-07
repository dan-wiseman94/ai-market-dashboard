"""Pure-ish book analytics over the unified exposure list. Each function tolerates
empty input and never raises out of the deterministic core."""

from __future__ import annotations

from apps.book import constants as C
from apps.strategy.regime.services.compute import current_regime


def concentration(exposures: list[dict]) -> dict:
    total = sum(e["abs_exposure"] for e in exposures)
    if total <= 0:
        return {"total_abs": 0.0, "top_n_share": 0.0, "net_long": 0.0, "net_short": 0.0, "hhi": 0.0}
    top = sorted(exposures, key=lambda e: e["abs_exposure"], reverse=True)[: C.TOP_N]
    top_share = sum(e["abs_exposure"] for e in top) / total
    net_long = sum(e["net_signed"] for e in exposures if e["net_signed"] > 0)
    net_short = sum(e["net_signed"] for e in exposures if e["net_signed"] < 0)
    hhi = sum((e["abs_exposure"] / total) ** 2 for e in exposures)
    return {
        "total_abs": total,
        "top_n_share": top_share,
        "net_long": net_long,
        "net_short": net_short,
        "hhi": hhi,
    }


def near_invalidation() -> list[dict]:
    """Open theses whose current price sits within NEAR_INVALIDATION_PCT of their
    own invalidation_price — correlated stop-out risk. Best-effort per thesis."""
    from django.utils import timezone

    from apps.market.returns import nearest_bar_close
    from apps.thesis.models import Thesis

    now = timezone.now()
    out: list[dict] = []
    for t in Thesis.objects.filter(status="open").exclude(invalidation_price=None):
        inv_dec = t.invalidation_price
        if inv_dec is None:  # excluded above; narrows Decimal | None for the type checker
            continue
        inv = float(inv_dec)
        if inv <= 0:
            continue
        last = nearest_bar_close(t.ticker.upper(), now)
        if last is None:
            continue
        pct = abs(last - inv) / inv * 100.0
        if pct <= C.NEAR_INVALIDATION_PCT:
            out.append({"ticker": t.ticker.upper(), "thesis_id": t.id, "pct_to_invalidation": pct})
    out.sort(key=lambda r: r["pct_to_invalidation"])
    return out


def regime_fit(exposures: list[dict]) -> dict:
    """Directional alignment of the book's net tilt vs the current regime composite."""
    reading = current_regime()
    if reading is None:
        return {"regime": None, "alignment": "unknown", "note": "no regime reading"}
    net = sum(e["net_signed"] for e in exposures)
    composite = reading.composite
    risk_off = composite in ("Risk-Off", "Stress")
    if net > 0 and risk_off:
        alignment, note = "misaligned", "net-long book into a risk-off regime"
    elif net < 0 and not risk_off:
        alignment, note = "misaligned", "net-short book into a risk-on regime"
    elif net == 0:
        alignment, note = "neutral", "book is directionally flat"
    else:
        alignment, note = "aligned", "book tilt matches the regime"
    return {"regime": composite, "alignment": alignment, "note": note, "net_signed": net}
