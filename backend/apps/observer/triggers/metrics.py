"""Build a MetricsSnapshot dict for one beat tick.

This is the only module in apps.triggers that talks to Schwab + Redis.
The evaluator is pure and consumes whatever dict we return here.
"""

from __future__ import annotations

import contextlib
import logging
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

import redis
from django.conf import settings

from apps.market.services.fundamentals import fetch_fundamentals
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.observer.models import EventTrigger
from apps.observer.triggers import indicators as ind
from apps.observer.triggers.dsl import (
    DAILY_ONLY_METRICS,
    FUNDAMENTAL_METRICS,
    INDICATOR_METRICS,
    PARAMS_SPEC,
)
from apps.observer.triggers.evaluator import CROSSING_OPS, MetricsSnapshot, iter_leaves, leaf_key

log = logging.getLogger(__name__)

_WINDOW_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
_VOL_SAMPLES = 30  # rolling baseline length for volume_z
_VOL_MIN_SAMPLES = 3  # intervals needed before a z-score is meaningful
_OHLC_MAX_TTL = 3600  # daily bars barely move intraday


def _resolved_params(leaf: dict) -> dict:
    spec = PARAMS_SPEC.get(leaf["metric"], {})
    p = dict(leaf.get("params") or {})
    for k, (_t, default, *_r) in spec.items():
        p.setdefault(k, default)
    return p


def _bars_needed(leaves: list[dict]) -> int:
    need = 30
    for lf in leaves:
        pr = _resolved_params(lf)
        need = max(
            need,
            pr.get("period", 0) + 1,
            pr.get("slow", 0) + 1,
            252 if lf["metric"].startswith("dist_from_52w") else 0,
        )
    return min(need + 5, 500)


def _read_redis_str(r: redis.Redis, key: str) -> str | None:
    try:
        raw = r.get(key)
    except Exception as exc:
        log.warning("trigger.metrics.redis_get_failed key=%s: %s", key, exc)
        return None
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode()
    return str(raw)


def _ohlc_history(r: redis.Redis, ticker: str, timeframe: str, bars: int) -> list[dict]:
    import json

    key = f"trigger:ohlc:{ticker}:{timeframe}:{bars}"
    cached = _read_redis_str(r, key)
    if cached:
        try:
            return json.loads(cached)
        except ValueError:
            pass
    try:
        data = fetch_ohlc(ticker, timeframe=timeframe, bars=bars)
    except Exception as exc:
        log.warning("trigger.metrics.ohlc_failed %s/%s: %s", ticker, timeframe, exc)
        return []
    ttl = min(_WINDOW_SECONDS.get(timeframe, 60), _OHLC_MAX_TTL)
    with contextlib.suppress(Exception):
        r.setex(key, ttl, json.dumps(data))
    return data


def _indicator_value(
    metric: str,
    params: dict,
    closes: list[float],
    bars: list[dict],
    last: float | None,
) -> float | None:
    if last is None and metric not in ("rsi", "sma_spread_pct"):
        return None
    if metric == "rsi":
        return ind.rsi(closes, params["period"])
    if metric == "sma_spread_pct":
        return ind.sma_spread_pct(closes, fast=params["fast"], slow=params["slow"])
    if last is None:
        return None
    if metric == "atr_pct":
        return ind.atr_pct(bars, period=params["period"], last=last)
    if metric == "dist_from_sma_pct":
        return ind.dist_from_sma_pct(closes, period=params["period"], last=last)
    if metric == "dist_from_52w_high":
        return ind.dist_from_high([float(b["high"]) for b in bars], last=last)
    if metric == "dist_from_52w_low":
        return ind.dist_from_low([float(b["low"]) for b in bars], last=last)
    if metric == "gap_pct":
        if len(bars) < 2:
            return None
        return ind.gap_pct(
            today_open=float(bars[-1]["open"]),
            prev_close=float(bars[-2]["close"]),
        )
    return None


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
    ctx = _LeafContext(
        quotes=quotes,
        positions_total_pl=positions_total_pl,
        positions_total_mkt=positions_total_mkt,
        earnings_days=earnings_days,
        fundamentals_cache={},
    )
    r = _redis()
    for leaf in leaves:
        _record_leaf(r, snapshot, leaf, ctx)

    try:
        r.setex("trigger:last_tick_at", 120, str(int(time.time())))
    except Exception as exc:
        log.warning("trigger.metrics.last_tick_at_failed: %s", exc)

    return snapshot


@dataclass
class _LeafContext:
    """Per-tick inputs shared across the leaf recorders (assembled once in build_snapshot)."""

    quotes: dict[str, dict]
    positions_total_pl: float | None
    positions_total_mkt: float | None
    earnings_days: dict[str, int]
    fundamentals_cache: dict[str, dict]


_FUND_METRIC_KEY = {
    "pe_ratio": "pe",
    "market_cap": "market_cap",
    "revenue_growth": "rev_growth_yoy",
    "gross_margin": "gross_margin",
}


def _record_leaf(
    r: redis.Redis, snapshot: dict[str, float | None], leaf: dict, ctx: _LeafContext
) -> None:
    """Dispatch one leaf to its metric recorder, writing the result into ``snapshot``."""
    metric = leaf["metric"]
    op = leaf["op"]
    window = leaf.get("window")
    ticker = leaf.get("ticker")
    key = leaf_key(leaf)

    if metric == "price":
        assert ticker is not None
        _record_last_metric(
            r, snapshot, key=key, symbol=ticker, op=op, quote=ctx.quotes.get(ticker)
        )
    elif metric == "vix":
        _record_last_metric(
            r, snapshot, key=key, symbol="$VIX", op=op, quote=ctx.quotes.get("$VIX")
        )
    elif metric == "pct_change":
        assert ticker is not None and window is not None
        _record_pct_change(r, snapshot, key, ticker, window, ctx.quotes)
    elif metric == "volume_z":
        assert ticker is not None and window is not None
        # _volume_z mutates the rolling Redis baseline, so compute once per
        # (ticker, window) even when several triggers share the same leaf.
        if key not in snapshot:
            snapshot[key] = _volume_z(r, ticker, window, _extract_volume(ctx.quotes.get(ticker)))
    elif metric == "position_pl":
        snapshot[key] = ctx.positions_total_pl
    elif metric == "position_pl_pct":
        if ctx.positions_total_mkt and ctx.positions_total_mkt > 0:
            snapshot[key] = (ctx.positions_total_pl or 0) / ctx.positions_total_mkt
        else:
            snapshot[key] = None
    elif metric == "days_to_earnings":
        assert ticker is not None
        snapshot[key] = ctx.earnings_days.get(ticker.upper())
    elif metric in FUNDAMENTAL_METRICS:
        assert ticker is not None
        _record_fundamental(snapshot, key, metric, ticker, ctx.fundamentals_cache)
    elif metric in INDICATOR_METRICS:
        assert ticker is not None
        _record_indicator(r, snapshot, leaf, metric, ticker, window, op, ctx.quotes)


def _record_pct_change(
    r: redis.Redis,
    snapshot: dict[str, float | None],
    key: str,
    ticker: str,
    window: str,
    quotes: dict,
) -> None:
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


def _record_fundamental(
    snapshot: dict[str, float | None], key: str, metric: str, ticker: str, cache: dict[str, dict]
) -> None:
    fund = cache.get(ticker.upper())
    if fund is None:
        fund = fetch_fundamentals(ticker.upper())
        cache[ticker.upper()] = fund
    raw_val = fund.get(_FUND_METRIC_KEY[metric])
    if raw_val is not None:
        snapshot[key] = float(raw_val)
    # absent when fund == {} or value is None — evaluator treats missing key as no-match


def _record_indicator(
    r: redis.Redis,
    snapshot: dict[str, float | None],
    leaf: dict,
    metric: str,
    ticker: str,
    window: Any,
    op: str,
    quotes: dict,
) -> None:
    tf = "1d" if metric in DAILY_ONLY_METRICS else window
    params = _resolved_params(leaf)
    resolved_key = leaf_key({**leaf, "params": params})
    if resolved_key in snapshot:
        return
    history = _ohlc_history(r, ticker, tf, _bars_needed([leaf]))
    closes = [float(b["close"]) for b in history if b.get("close") is not None]
    last = _extract_last(quotes.get(ticker)) or (closes[-1] if closes else None)
    value = _indicator_value(metric, params, closes, history, last)
    snapshot[resolved_key] = value
    if op in CROSSING_OPS:
        last_key = f"trigger:last:{resolved_key}"
        snapshot[f"_prior:{resolved_key}"] = _read_redis_float(r, last_key)
        if value is not None:
            r.setex(last_key, _OHLC_MAX_TTL, str(value))


def _earnings_days_map(leaves: list[dict]) -> dict[str, int]:
    """Soonest upcoming-earnings countdown (in days) per ticker, batched into one query."""
    from django.utils import timezone

    from apps.market.models import MarketEvent

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
        if leaf.get("ticker")
        and leaf["metric"] in {"price", "pct_change", "volume_z"} | INDICATOR_METRICS
    }


def _record_last_metric(
    r: redis.Redis,
    snapshot: dict[str, float | None],
    *,
    key: str,
    symbol: str,
    op: str,
    quote: dict | None,
) -> None:
    """Record a last-price metric (price/vix): current value, crossing prior, cached last."""
    last = _extract_last(quote)
    snapshot[key] = last
    last_key = f"trigger:last:{symbol}"
    if op in CROSSING_OPS:
        snapshot[f"_prior:{key}"] = _read_redis_float(r, last_key)
    if last is not None:
        r.setex(last_key, 60, str(last))


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
