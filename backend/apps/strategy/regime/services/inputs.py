"""Best-effort gather of raw regime inputs. NEVER raises — each source is isolated
and degrades to None/{} so a missing feed only blanks one axis."""

from __future__ import annotations

import logging

from apps.market.models import OHLCBar
from apps.market.services.context import fetch_market_context
from apps.market.services.fred import fetch_macro
from apps.strategy.regime import constants as C
from apps.triggers.indicators import dist_from_sma_pct, sma_spread_pct

log = logging.getLogger(__name__)


def _daily_closes(ticker: str, limit: int) -> list[float]:
    rows = list(
        OHLCBar.objects.filter(ticker=ticker, timeframe="1d")
        .order_by("-ts")
        .values_list("close", flat=True)[:limit]
    )
    return [float(c) for c in reversed(rows)]  # oldest -> newest


def _vix_percentile(vix_last: float | None, closes: list[float]) -> float | None:
    if vix_last is None or len(closes) < 30:
        return None
    below = sum(1 for c in closes if c <= vix_last)
    return below / len(closes)


def _sector_returns() -> dict:
    out: dict[str, float] = {}
    for etf in C.OFFENSIVE_ETFS + C.DEFENSIVE_ETFS:
        closes = _daily_closes(etf, C.SECTOR_RETURN_WINDOW)
        if len(closes) >= 2 and closes[0]:
            out[etf] = (closes[-1] / closes[0] - 1.0) * 100.0
    return out


def gather_inputs() -> dict:
    out: dict = {
        "vix_last": None,
        "vix_percentile": None,
        "spx_ma_spread": None,
        "spx_dist_50": None,
        "breadth": {},
        "sector_returns": {},
        "t10y2y": None,
        "tnx_change": None,
    }
    try:
        ctx = fetch_market_context()
        out["vix_last"] = ctx.get("vix_last")
        out["breadth"] = ctx.get("breadth") or {}
    except Exception:
        log.warning("regime.inputs.context_failed", exc_info=True)
    try:
        vix_closes = _daily_closes("$VIX", C.VIX_PERCENTILE_WINDOW)
        out["vix_percentile"] = _vix_percentile(out["vix_last"], vix_closes)
    except Exception:
        log.warning("regime.inputs.vix_pct_failed", exc_info=True)
    try:
        spx = _daily_closes("$SPX", C.MA_SLOW + 5)
        if spx:
            out["spx_ma_spread"] = sma_spread_pct(spx, fast=C.MA_FAST, slow=C.MA_SLOW)
            out["spx_dist_50"] = dist_from_sma_pct(spx, period=C.MA_FAST, last=spx[-1])
    except Exception:
        log.warning("regime.inputs.spx_trend_failed", exc_info=True)
    try:
        out["sector_returns"] = _sector_returns()
    except Exception:
        log.warning("regime.inputs.sector_returns_failed", exc_info=True)
    try:
        macro = fetch_macro(["T10Y2Y", "DGS10"])
        out["t10y2y"] = (macro.get("T10Y2Y") or {}).get("value")
        out["tnx_change"] = (macro.get("DGS10") or {}).get("change")
    except Exception:
        log.warning("regime.inputs.macro_failed", exc_info=True)
    return out
