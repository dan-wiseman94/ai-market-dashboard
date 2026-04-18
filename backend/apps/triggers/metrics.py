"""Build a MetricsSnapshot dict for one beat tick.

This is the only module in apps.triggers that talks to Schwab + Redis.
The evaluator is pure and consumes whatever dict we return here.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any, cast

import redis
from django.conf import settings

from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.triggers.evaluator import MetricsSnapshot
from apps.triggers.models import EventTrigger

log = logging.getLogger(__name__)

_WINDOW_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def build_snapshot(triggers: Iterable[EventTrigger]) -> MetricsSnapshot:
    """Populate the flat metrics dict the evaluator will read."""
    leaves = _collect_leaves(triggers)
    tickers = _ticker_union(leaves)
    needs_positions = any(leaf["metric"].startswith("position_") for leaf in leaves)
    has_vix = any(leaf["metric"] == "vix" for leaf in leaves)

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

        if metric == "price":
            assert ticker is not None
            key = f"price:{ticker}"
            last = _extract_last(quotes.get(ticker))
            snapshot[key] = last
            if op in ("crosses_above", "crosses_below"):
                prior = _read_redis_float(r, f"trigger:last:{ticker}")
                snapshot[f"_prior:{key}"] = prior
            if last is not None:
                r.setex(f"trigger:last:{ticker}", 60, str(last))

        elif metric == "vix":
            last = _extract_last(quotes.get("$VIX"))
            snapshot["vix"] = last
            if op in ("crosses_above", "crosses_below"):
                prior = _read_redis_float(r, "trigger:last:$VIX")
                snapshot["_prior:vix"] = prior
            if last is not None:
                r.setex("trigger:last:$VIX", 60, str(last))

        elif metric == "pct_change":
            assert ticker is not None and window is not None
            key = f"pct_change:{ticker}:{window}"
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

        elif metric == "position_pl":
            snapshot["position_pl"] = positions_total_pl

        elif metric == "position_pl_pct":
            if positions_total_mkt and positions_total_mkt > 0:
                snapshot["position_pl_pct"] = (positions_total_pl or 0) / positions_total_mkt
            else:
                snapshot["position_pl_pct"] = None

    try:
        r.setex("trigger:last_tick_at", 120, str(int(time.time())))
    except Exception as exc:
        log.warning("trigger.metrics.last_tick_at_failed: %s", exc)

    return snapshot


def _collect_leaves(triggers: Iterable[EventTrigger]) -> list[dict]:
    leaves: list[dict] = []
    for t in triggers:
        _walk(t.condition, leaves)
    return leaves


def _walk(node: Any, out: list[dict]) -> None:
    if not isinstance(node, dict):
        return
    if "all" in node:
        for c in node["all"]:
            _walk(c, out)
        return
    if "any" in node:
        for c in node["any"]:
            _walk(c, out)
        return
    if "not" in node:
        _walk(node["not"], out)
        return
    if "metric" in node:
        out.append(node)


def _ticker_union(leaves: list[dict]) -> set[str]:
    return {
        leaf["ticker"]
        for leaf in leaves
        if leaf.get("ticker") and leaf["metric"] in ("price", "pct_change")
    }


def _extract_last(quote_blob: dict | None) -> float | None:
    if not quote_blob:
        return None
    last = quote_blob.get("last")
    return float(last) if last is not None else None


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
