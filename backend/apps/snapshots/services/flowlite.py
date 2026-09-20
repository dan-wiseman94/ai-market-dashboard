"""Volume-based flow-pressure proxy. NOT fund-flow data — no free per-ETF
flow source exists (spec 6.2); every render of this payload says so."""

from __future__ import annotations

import logging
import statistics

from django.utils import timezone

from apps.market.models import OHLCBar, OptionChainSnapshot

log = logging.getLogger(__name__)

PROXY_NOTE = "volume-based flow proxy — not fund-flow data"
_CORE = ["SPY", "QQQ"]


def build_flowlite_payload(*, watchlist_tickers: list[str], primary: str) -> dict:
    from apps.market.services.context import SECTOR_ETFS

    tickers = _CORE + [s for s in SECTOR_ETFS if s not in _CORE]
    volume_z = sorted(
        (z for t in tickers if (z := _volume_zscore(t)) is not None),
        key=lambda r: abs(r["z"]),
        reverse=True,
    )
    return {
        "proxy_note": PROXY_NOTE,
        "volume_z": volume_z,
        "put_call_delta": _put_call_delta(primary),
        "unusual": _unusual(primary),
    }


def _volume_zscore(ticker: str, *, window: int = 20) -> dict | None:
    vols = [
        float(b.volume or 0)
        for b in OHLCBar.objects.filter(ticker=ticker.upper(), timeframe="1d").order_by("-ts")[
            : window + 1
        ]
    ]
    if len(vols) < window + 1:
        return None
    latest, hist = vols[0], vols[1:]
    stdev = statistics.pstdev(hist)
    if not stdev:
        return None
    return {
        "ticker": ticker.upper(),
        "z": round((latest - statistics.fmean(hist)) / stdev, 2),
        "latest": int(latest),
        "avg": int(statistics.fmean(hist)),
    }


def _put_call_delta(primary: str) -> dict | None:
    from apps.market.services.option_analytics import put_call_from_expiries

    rows = list(
        OptionChainSnapshot.objects.filter(ticker=primary.upper()).order_by("-fetched_at")[:2]
    )
    if len(rows) < 2:
        return None
    latest = put_call_from_expiries(rows[0].payload.get("expiries") or {}).get("volume_ratio")
    prior = put_call_from_expiries(rows[1].payload.get("expiries") or {}).get("volume_ratio")
    if latest is None or prior is None:
        return None
    return {
        "ticker": primary.upper(),
        "latest": latest,
        "prior": prior,
        "delta": round(latest - prior, 4),
    }


def _unusual(primary: str) -> list:
    try:
        from apps.analytics.services.unusual_options import unusual_options

        return list(unusual_options(ticker=primary.upper(), at=timezone.now(), top_n=3))
    except Exception as exc:
        log.debug("flowlite unusual-options skipped: %s", exc)
        return []
