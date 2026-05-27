"""Build a MetricsSnapshot dict for one beat tick.

This is the only module in apps.triggers that talks to Schwab + Redis.
The evaluator is pure and consumes whatever dict we return here.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections.abc import Iterable
from typing import cast

import redis
from django.conf import settings

from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.triggers.evaluator import CROSSING_OPS, MetricsSnapshot, iter_leaves, leaf_key
from apps.triggers.models import EventTrigger

log = logging.getLogger(__name__)

_WINDOW_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
_VOL_SAMPLES = 30  # rolling baseline length for volume_z
_VOL_MIN_SAMPLES = 3  # intervals needed before a z-score is meaningful


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def build_snapshot(triggers: Iterable[EventTrigger]) -> MetricsSnapshot:
    """Populate the flat metrics dict the evaluator will read."""
    leaves = [leaf for t in triggers for leaf in iter_leaves(t.condition)]
    tickers = _ticker_union(leaves)
    needs_positions = any(leaf["metric"].startswith("position_") for leaf in leaves)
    has_vix = any(leaf["metric"] == "vix" for leaf in leaves)
    earnings_days = _earnings_days_map(leaves)

    quote_tickers = set(tickers)
    if has_vix:
        quote_tickers.add("$VIX")

    quotes: dict[str, dict] = {}
    if quote_tickers:
        try:
            quotes = fetch_quotes(sorted(quote_tickers))
        except Exception as exc:
            log.warning("trigger.metrics.quotes_failed: %s", exc)

    positions_total_pl: float | None = None
    positions_total_mkt: float | None = None
    if needs_positions:
        try:
            rows = fetch_positions()
            positions_total_pl = sum((r.get("unrealized_pl") or 0) for r in rows) or 0.0
            positions_total_mkt = sum((r.get("mkt_value") or 0) for r in rows) or 0.0
        except Exception as exc:
            log.warning("trigger.metrics.positions_failed: %s", exc)

    snapshot: dict[str, float | None] = {}
    r = _redis()

    for leaf in leaves:
        metric = leaf["metric"]
        op = leaf["op"]
        window = leaf.get("window")
        ticker = leaf.get("ticker")
        key = leaf_key(leaf)

        if metric == "price":
            assert ticker is not None
            last = _extract_last(quotes.get(ticker))
            snapshot[key] = last
            if op in CROSSING_OPS:
                snapshot[f"_prior:{key}"] = _read_redis_float(r, f"trigger:last:{ticker}")
            if last is not None:
                r.setex(f"trigger:last:{ticker}", 60, str(last))

        elif metric == "vix":
            last = _extract_last(quotes.get("$VIX"))
            snapshot[key] = last
            if op in CROSSING_OPS:
                snapshot[f"_prior:{key}"] = _read_redis_float(r, "trigger:last:$VIX")
            if last is not None:
                r.setex("trigger:last:$VIX", 60, str(last))

        elif metric == "pct_change":
            assert ticker is not None and window is not None
            last = _extract_last(quotes.get(ticker))
            window_key = f"trigger:window:{ticker}:{window}"
            prior = _read_redis_float(r, window_key)
            if last is None:
                snapshot[key] = None
            elif prior is None:
                snapshot[key] = None
                r.setex(window_key, 2 * _WINDOW_SECONDS[window], str(last))
            else:
                snapshot[key] = (last - prior) / prior if prior != 0 else None
                if not r.exists(window_key):
                    r.setex(window_key, 2 * _WINDOW_SECONDS[window], str(last))

        elif metric == "volume_z":
            assert ticker is not None and window is not None
            # _volume_z mutates the rolling Redis baseline, so compute once per
            # (ticker, window) even when several triggers share the same leaf.
            if key not in snapshot:
                snapshot[key] = _volume_z(r, ticker, window, _extract_volume(quotes.get(ticker)))

        elif metric == "position_pl":
            snapshot[key] = positions_total_pl

        elif metric == "position_pl_pct":
            if positions_total_mkt and positions_total_mkt > 0:
                snapshot[key] = (positions_total_pl or 0) / positions_total_mkt
            else:
                snapshot[key] = None

        elif metric == "days_to_earnings":
            assert ticker is not None
            snapshot[key] = earnings_days.get(ticker.upper())

    try:
        r.setex("trigger:last_tick_at", 120, str(int(time.time())))
    except Exception as exc:
        log.warning("trigger.metrics.last_tick_at_failed: %s", exc)

    return snapshot


def _earnings_days_map(leaves: list[dict]) -> dict[str, int]:
    """Soonest upcoming-earnings countdown (in days) per ticker, batched into one query."""
    from apps.market.models import MarketEvent
    from django.utils import timezone

    tickers = {
        leaf["ticker"].upper()
        for leaf in leaves
        if leaf["metric"] == "days_to_earnings" and leaf.get("ticker")
    }
    if not tickers:
        return {}
    now = timezone.now()
    today = now.date()
    rows = MarketEvent.objects.filter(
        kind="earnings", ticker__in=tickers, event_time__gte=now
    ).order_by("ticker", "event_time")
    out: dict[str, int] = {}
    for r in rows:
        if r.ticker not in out:  # first row per ticker is the soonest
            out[r.ticker] = (r.event_time.date() - today).days
    return out


def _ticker_union(leaves: list[dict]) -> set[str]:
    return {
        leaf["ticker"]
        for leaf in leaves
        if leaf.get("ticker") and leaf["metric"] in ("price", "pct_change", "volume_z")
    }


def _extract_last(quote_blob: dict | None) -> float | None:
    if not quote_blob:
        return None
    last = quote_blob.get("last")
    return float(last) if last is not None else None


def _extract_volume(quote_blob: dict | None) -> float | None:
    if not quote_blob:
        return None
    vol = quote_blob.get("volume")
    return float(vol) if vol is not None else None


def _zscore(latest: float, baseline: list[float]) -> float | None:
    """z-score of `latest` against `baseline` (which includes it).

    Returns None when there are too few samples to be meaningful or the baseline
    is flat (zero variance) — the evaluator treats None as a non-match.
    """
    if len(baseline) < _VOL_MIN_SAMPLES:
        return None
    std = statistics.pstdev(baseline)
    if std == 0:
        return None
    return (latest - statistics.fmean(baseline)) / std


def _volume_z(r: redis.Redis, ticker: str, window: str, cur_volume: float | None) -> float | None:
    """z-score of the latest per-interval volume against a rolling baseline.

    Quote volume is cumulative daily (Schwab totalVolume), so the interval volume
    is `cur - prior`. We keep the last _VOL_SAMPLES intervals per (ticker, window)
    in a capped Redis list. Returns None on cold start, on a cumulative reset
    (day rollover: cur < prior), or until the baseline is large enough.
    """
    if cur_volume is None:
        return None
    prev_key = f"trigger:volprev:{ticker}"
    list_key = f"trigger:volwin:{ticker}:{window}"
    ttl = 4 * _WINDOW_SECONDS[window]
    prior = _read_redis_float(r, prev_key)
    r.setex(prev_key, ttl, str(cur_volume))
    if prior is None or cur_volume < prior:
        return None
    interval = cur_volume - prior
    r.lpush(list_key, str(interval))
    r.ltrim(list_key, 0, _VOL_SAMPLES - 1)
    r.expire(list_key, ttl)
    try:
        raw = cast("list[bytes | str]", r.lrange(list_key, 0, -1))
        samples = [float(x.decode() if isinstance(x, bytes) else x) for x in raw]
    except (ValueError, TypeError) as exc:
        log.warning("trigger.metrics.volume_z_parse_failed key=%s: %s", list_key, exc)
        return None
    return _zscore(interval, samples)


def _read_redis_float(r: redis.Redis, key: str) -> float | None:
    try:
        raw = r.get(key)
    except Exception as exc:
        log.warning("trigger.metrics.redis_get_failed key=%s: %s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return float(cast("bytes | str", raw))
    except (ValueError, TypeError):
        return None
