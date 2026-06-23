"""Options-implied expected move (1σ) from a stored OptionChainSnapshot payload.

Deterministic and defensive: never raises; returns ``None`` / ``[]`` on a missing
chain or absent IV. The 1σ move over ``H`` days is ``atm_iv × sqrt(H/365)`` — the
~68% band the options market is pricing — using the ATM IV of the chain expiry
nearest ``H`` (no interpolation). Feeds the AI snapshot context and freezes onto a
prediction so reality can be scored against what was priced.
"""

from __future__ import annotations

import math
from datetime import date, datetime

_DEFAULT_HORIZONS = (7, 30, 90)


def _norm_iv(atm_iv: float | None) -> float | None:
    """IV as a decimal fraction. Schwab's ``volatility`` field is a percent
    (``25.0`` → ``0.25``); an annualized IV above ~300% is implausible, so any value
    > 3.0 is treated as a percent and divided by 100. Non-positive → None."""
    if atm_iv is None:
        return None
    try:
        iv = float(atm_iv)
    except (TypeError, ValueError):
        return None
    if iv <= 0:
        return None
    return iv / 100.0 if iv > 3.0 else iv


def one_sigma_pct(atm_iv: float | None, horizon_days: int) -> float | None:
    """1σ expected move as a fraction of spot, or None on bad input."""
    iv = _norm_iv(atm_iv)
    if iv is None or horizon_days <= 0:
        return None
    return iv * math.sqrt(horizon_days / 365.0)


def _today() -> date:
    from django.utils import timezone

    return timezone.now().date()


def _dte(expiry: str, *, today: date) -> int | None:
    try:
        d = date.fromisoformat(expiry[:10]) if not isinstance(expiry, datetime) else expiry.date()
    except (TypeError, ValueError):
        return None
    return (d - today).days


def _atm_iv_by_expiry(payload: dict) -> dict[str, float]:
    """``{expiry: atm_iv}`` via option_analytics.chain_analytics' term structure."""
    from apps.market.services.option_analytics import chain_analytics

    expiries = (payload or {}).get("expiries") or {}
    flat: list[dict] = []
    for exp, section in expiries.items():
        if not isinstance(section, dict):
            continue
        for c in section.get("calls", []):
            flat.append({**c, "side": "call", "expiry": exp})
        for c in section.get("puts", []):
            flat.append({**c, "side": "put", "expiry": exp})
    if not flat:
        return {}
    underlying = (payload or {}).get("underlying_last")
    try:
        spot = float(underlying) if underlying else None
    except (TypeError, ValueError):
        spot = None
    ts = chain_analytics(flat, spot=spot).get("term_structure") or []
    return {row["expiry"]: row["atm_iv"] for row in ts if row.get("atm_iv") is not None}


def _nearest_atm_iv(by_exp: dict[str, float], horizon_days: int, *, today: date) -> float | None:
    """ATM IV of the expiry whose days-to-expiration is nearest ``horizon_days``
    (only future expiries)."""
    best: tuple[int, float] | None = None
    for exp, iv in by_exp.items():
        dte = _dte(exp, today=today)
        if dte is None or dte <= 0:
            continue
        diff = abs(dte - horizon_days)
        if best is None or diff < best[0]:
            best = (diff, iv)
    return best[1] if best else None


def for_horizon(payload: dict, horizon_days: int, *, today: date | None = None) -> float | None:
    """1σ expected-move fraction over ``horizon_days`` from the nearest expiry's ATM IV."""
    by_exp = _atm_iv_by_expiry(payload)
    if not by_exp:
        return None
    iv = _nearest_atm_iv(by_exp, horizon_days, today=today or _today())
    return one_sigma_pct(iv, horizon_days)


def term_structure(
    payload: dict, *, horizons: tuple[int, ...] = _DEFAULT_HORIZONS, today: date | None = None
) -> list[dict]:
    """``[{horizon_days, move_pct, move_abs}]`` for each horizon, or ``[]`` on no IV."""
    by_exp = _atm_iv_by_expiry(payload)
    if not by_exp:
        return []
    today = today or _today()
    underlying = (payload or {}).get("underlying_last")
    try:
        spot = float(underlying) if underlying else None
    except (TypeError, ValueError):
        spot = None
    out: list[dict] = []
    for h in horizons:
        iv = _nearest_atm_iv(by_exp, h, today=today)
        mp = one_sigma_pct(iv, h)
        if mp is None:
            continue
        out.append(
            {
                "horizon_days": h,
                "move_pct": round(mp, 4),
                "move_abs": round(spot * mp, 2) if spot else None,
            }
        )
    return out
