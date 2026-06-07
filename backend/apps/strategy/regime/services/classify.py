"""Pure regime classifiers: raw inputs -> axis labels -> composite.

Every function is total (handles None / empty -> "Unknown") and side-effect free,
so it is exhaustively unit-testable without any DB or network.
"""

from __future__ import annotations

from apps.strategy.regime import constants as C

UNKNOWN = C.UNKNOWN


def classify_volatility(vix_last: float | None, vix_percentile: float | None = None) -> str:
    if vix_last is None:
        return UNKNOWN
    v = float(vix_last)
    if v >= C.VIX_STRESS:
        return "Stress"  # genuine panic — an absolute-VIX signal; never reached via percentile
    if v >= C.VIX_ELEVATED:
        base = "Elevated"
    elif v >= C.VIX_LOW:
        base = "Normal"
    else:
        base = "Low"
    # Percentile-aware escalation: vol that is extreme RELATIVE to its own trailing window
    # (>= VIX_PERCENTILE_ELEVATED) is bumped one notch — surfacing "heating up vs its own
    # regime" even when the absolute level is moderate. Escalation-only (an absolute level is
    # never de-escalated) and capped at Elevated (percentile never manufactures "Stress").
    if vix_percentile is not None and vix_percentile >= C.VIX_PERCENTILE_ELEVATED:
        return {"Low": "Normal", "Normal": "Elevated"}.get(base, base)
    return base


def classify_trend(ma_spread: float | None, dist_50: float | None) -> str:
    if ma_spread is None and dist_50 is None:
        return UNKNOWN
    above_50 = dist_50 is not None and dist_50 > 0
    golden = ma_spread is not None and ma_spread > 0
    if above_50 and golden:
        return "Uptrend"
    below_50 = dist_50 is not None and dist_50 < 0
    death = ma_spread is not None and ma_spread < 0
    if below_50 and death:
        return "Downtrend"
    return "Range"


def classify_breadth(breadth: dict) -> str:
    advn = breadth.get("$ADVN")
    decn = breadth.get("$DECN")
    trin = breadth.get("$TRIN")
    if advn is None or decn is None or (advn + decn) == 0:
        return UNKNOWN
    if trin is not None and trin >= C.TRIN_DETERIORATING:
        return "Deteriorating"
    ratio = advn / (advn + decn)
    if ratio >= C.BREADTH_BROAD:
        return "Broad"
    if ratio <= C.BREADTH_NARROW:
        return "Narrow"
    return "Mixed"


def classify_leadership(sector_returns: dict) -> str:
    off = [sector_returns[t] for t in C.OFFENSIVE_ETFS if t in sector_returns]
    deff = [sector_returns[t] for t in C.DEFENSIVE_ETFS if t in sector_returns]
    if not off or not deff:
        return UNKNOWN
    spread = (sum(off) / len(off)) - (sum(deff) / len(deff))
    if spread >= C.LEADERSHIP_SPREAD:
        return "Offensive"
    if spread <= -C.LEADERSHIP_SPREAD:
        return "Defensive"
    return "Mixed"


def classify_rates(t10y2y: float | None, tnx_change: float | None) -> str:
    if t10y2y is None:
        return UNKNOWN
    if t10y2y < 0:
        return "Inverted"
    if tnx_change is not None and tnx_change > 0:
        return "Tightening"
    if tnx_change is not None and tnx_change < 0:
        return "Easing"
    return "Steepening"


_RISK_ON = {
    "volatility": {"Low", "Normal"},
    "trend": {"Uptrend"},
    "breadth": {"Broad"},
    "leadership": {"Offensive"},
    "rates": {"Easing", "Steepening"},
}
_RISK_OFF = {
    "volatility": {"Elevated"},
    "trend": {"Downtrend"},
    "breadth": {"Narrow", "Deteriorating"},
    "leadership": {"Defensive"},
    "rates": {"Inverted", "Tightening"},
}


def fold_composite(axes: dict[str, str]) -> str:
    if axes.get("volatility") == "Stress":
        return "Stress"
    score = 0
    for axis, label in axes.items():
        if label in _RISK_ON.get(axis, set()):
            score += 1
        elif label in _RISK_OFF.get(axis, set()):
            score -= 1
    if score >= C.COMPOSITE_RISK_ON:
        return "Risk-On"
    if score <= C.COMPOSITE_RISK_OFF:
        return "Risk-Off"
    return "Neutral-Transitional"


def build_drivers(axes: dict[str, str], inp: dict) -> list[str]:
    drivers: list[str] = []
    vix = inp.get("vix_last")
    if vix is not None:
        s = f"VIX {float(vix):.0f}"
        pct = inp.get("vix_percentile")
        if pct is not None:
            s += f" ({pct:.0%}ile)"
        drivers.append(f"{s} — {axes.get('volatility')}")
    for axis, prefix in [
        ("trend", "SPX trend"),
        ("breadth", "breadth"),
        ("leadership", None),
        ("rates", "rates"),
    ]:
        label = axes.get(axis)
        if not label or label == UNKNOWN:
            continue
        if axis == "leadership":
            drivers.append(f"{label} leadership")
        else:
            drivers.append(f"{prefix} {label}")
    return drivers
