"""Flag unusual option lines in the most recent chain snapshot.

A line is unusual if:
  - volume_ratio = volume / max(oi, 1) >= 3.0, OR
  - iv_z >= 1.5 sigma above the 30-day mean IV for the same chain

We return both flags + a composite score = volume_ratio + max(iv_z, 0).
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from apps.market.models import OptionChainSnapshot

_VOLUME_RATIO_THRESHOLD = 3.0
_IV_Z_THRESHOLD = 1.5


def unusual_options(*, ticker: str, at: datetime, top_n: int = 25) -> list[dict]:
    ticker = ticker.upper()
    latest = (
        OptionChainSnapshot.objects.filter(ticker=ticker, fetched_at__lte=at)
        .order_by("-fetched_at")
        .first()
    )
    if latest is None:
        return []

    history = list(
        OptionChainSnapshot.objects.filter(
            ticker=ticker,
            fetched_at__gte=at - timedelta(days=30),
            fetched_at__lt=latest.fetched_at,
        ).order_by("fetched_at")
    )
    iv_mean, iv_stdev = _iv_stats(history)

    flagged: list[dict] = []
    expiries = (latest.payload or {}).get("expiries") or {}
    for expiry, sides in expiries.items():
        for side in ("calls", "puts"):
            for line in sides.get(side, []) or []:
                rec = _score_line(line, side, expiry, iv_mean, iv_stdev)
                if rec is not None:
                    flagged.append(rec)

    flagged.sort(key=lambda r: r["score"], reverse=True)
    return flagged[:top_n]


def _score_line(
    line: dict,
    side: str,
    expiry: str,
    iv_mean: float | None,
    iv_stdev: float | None,
) -> dict | None:
    volume = float(line.get("volume") or 0)
    oi = float(line.get("oi") or 0)
    iv = parse_iv(line.get("iv"))

    vol_ratio = volume / max(oi, 1.0)
    iv_z: float | None = None
    if iv is not None and iv_mean is not None and iv_stdev is not None and iv_stdev != 0:
        iv_z = (iv - iv_mean) / iv_stdev

    triggers = []
    if vol_ratio >= _VOLUME_RATIO_THRESHOLD:
        triggers.append("volume_vs_oi")
    if iv_z is not None and iv_z >= _IV_Z_THRESHOLD:
        triggers.append("iv_spike")
    if not triggers:
        return None

    score = vol_ratio + (iv_z if (iv_z is not None and iv_z > 0) else 0)
    return {
        "strike": line.get("strike"),
        "side": "call" if side == "calls" else "put",
        "expiry": expiry,
        "volume": int(volume),
        "oi": int(oi),
        "iv": iv,
        "volume_ratio": round(vol_ratio, 2),
        "iv_z": round(iv_z, 2) if iv_z is not None else None,
        "triggers": triggers,
        "score": round(score, 2),
    }


def parse_iv(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def iv_values(history: list[OptionChainSnapshot]) -> list[float]:
    """All parseable IV values across the historical chain snapshots."""
    ivs: list[float] = []
    for snap in history:
        expiries = (snap.payload or {}).get("expiries") or {}
        for sides in expiries.values():
            for side_key in ("calls", "puts"):
                for line in sides.get(side_key, []) or []:
                    iv = parse_iv(line.get("iv"))
                    if iv is not None:
                        ivs.append(iv)
    return ivs


def _iv_stats(history: list[OptionChainSnapshot]) -> tuple[float | None, float | None]:
    """Mean + stdev of IV values across the historical chain snapshots."""
    ivs = iv_values(history)
    if len(ivs) < 2:
        return (None, None)
    return (statistics.mean(ivs), statistics.stdev(ivs))
