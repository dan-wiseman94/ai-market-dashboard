"""Replay a trigger DSL against stored OHLC bars for a date range.

Builds a per-bar 'snapshot' shaped like what triggers.metrics emits at runtime,
then runs the existing evaluator. Supports price, pct_change, and indicator
leaves; live-only metrics (position_pl) are skipped when replaying.

VIX leaf support: when the condition references the ``vix`` metric, ``$VIX``
daily bars are loaded and aligned in-memory to each bar's timestamp. A bar
with no aligned ``$VIX`` entry leaves the ``vix`` key absent from that bar's
snapshot (coverage-honest; never fabricated).

Forward-return scoring note: ``fwd_1d_pct`` / ``fwd_5d_pct`` are computed
**after** the match decision and peek at bars that occur AFTER the match
timestamp. This is intentional — the point of scoring is to evaluate signal
quality with hindsight — but it means these fields carry a deliberate
look-ahead bias that is NOT causal. The ``matched`` flag itself is strictly
causal (uses only data up to and including that bar). Report scores via
``backtest_summary``, not the ``matched`` flag.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean

from apps.market.models import OHLCBar
from apps.observer.triggers import indicators as ind
from apps.observer.triggers.dsl import INDICATOR_METRICS, resolved_params
from apps.observer.triggers.evaluator import evaluate as evaluate_condition
from apps.observer.triggers.evaluator import iter_leaves, leaf_key


@dataclass
class BacktestMatch:
    ts: datetime
    values: dict[str, float | None]
    fwd_1d_pct: float | None = field(default=None)
    fwd_5d_pct: float | None = field(default=None)


def _load_vix_aligned(start: datetime, end: datetime) -> tuple[list[datetime], list[float]]:
    """Load $VIX daily bars in [start, end] as two parallel sorted lists.

    Returns (timestamps, closes) for use with bisect.  Both lists are sorted
    ascending by ts.  Used only when the condition contains a vix leaf.
    """
    vix_bars = (
        OHLCBar.objects.filter(
            ticker="$VIX",
            timeframe="1d",
            ts__gte=start,
            ts__lte=end,
        )
        .order_by("ts")
        .values_list("ts", "close")
    )
    vix_ts: list[datetime] = []
    vix_closes: list[float] = []
    for ts, close in vix_bars:
        vix_ts.append(ts)
        vix_closes.append(float(close))
    return vix_ts, vix_closes


def _vix_at(vix_ts: list[datetime], vix_closes: list[float], bar_ts: datetime) -> float | None:
    """Most-recent $VIX close at or before *bar_ts*, or None if no bar exists."""
    if not vix_ts:
        return None
    idx = bisect.bisect_right(vix_ts, bar_ts) - 1
    if idx < 0:
        return None
    return vix_closes[idx]


def backtest(
    condition: dict,
    *,
    start: datetime,
    end: datetime,
    timeframe: str = "1d",
) -> list[BacktestMatch]:
    """Replay the condition over daily closes between start and end.

    Each returned :class:`BacktestMatch` carries the match timestamp, the
    per-metric values that caused the match, and forward-return scores
    (``fwd_1d_pct``, ``fwd_5d_pct``) for signal-quality assessment.

    Look-ahead note: ``fwd_1d_pct`` / ``fwd_5d_pct`` are computed after the
    match decision using bars beyond the match timestamp — they are intentional
    look-ahead fields for post-hoc signal evaluation, NOT used in the causal
    ``matched`` decision.  Coverage-honest: either field is ``None`` when the
    required forward bar is unavailable (no stale fill).

    VIX coverage note: when the condition references a ``vix`` leaf, ``$VIX``
    daily bars are aligned in-memory.  If no ``$VIX`` bar exists at/before a
    given bar's timestamp, the ``vix`` key is absent from that bar's snapshot
    and the vix leaf will not match (no fabrication).

    IV-z / OptionChainSnapshot replay is deferred: chain history is too sparse
    for meaningful backtest replay until sustained ingestion runs.
    """
    from apps.market.returns import trading_day_forward_return_pct

    tickers = _unique_tickers(condition)
    if not tickers:
        return []

    # Detect whether the condition has a vix leaf so we only load $VIX when needed
    leaves = iter_leaves(condition)
    has_vix = any(leaf.get("metric") == "vix" for leaf in leaves)

    bars_qs = OHLCBar.objects.filter(
        ticker__in=tickers,
        ts__gte=start,
        ts__lte=end,
        timeframe=timeframe,
    ).order_by("ts")
    by_ts: dict[datetime, dict[str, OHLCBar]] = {}
    for bar in bars_qs:
        by_ts.setdefault(bar.ts, {})[bar.ticker] = bar

    # Load $VIX bars in-memory to avoid N per-bar queries
    vix_ts: list[datetime] = []
    vix_closes: list[float] = []
    if has_vix:
        vix_ts, vix_closes = _load_vix_aligned(start, end)

    closes_hist: dict[str, list[float]] = {}
    bars_hist: dict[str, list[dict]] = {}
    prev_values: dict[str, float | None] = {}
    matches: list[BacktestMatch] = []
    prev_closes: dict[str, float] = {}

    # We need a representative ticker for forward-return scoring.
    # Use the first ticker from the unique set (consistent; single-ticker conditions are the norm).
    score_ticker = next(iter(tickers))

    for ts in sorted(by_ts):
        per_ticker = by_ts[ts]
        snapshot: dict[str, float | None] = {}

        if has_vix:
            vix_val = _vix_at(vix_ts, vix_closes, ts)
            if vix_val is not None:
                snapshot["vix"] = vix_val
            # If vix_val is None, leave key absent — coverage-honest

        for ticker, bar in per_ticker.items():
            close = float(bar.close)
            high, low, op_price = float(bar.high), float(bar.low), float(bar.open)
            snapshot[f"price:{ticker}"] = close
            closes_hist.setdefault(ticker, []).append(close)
            bars_hist.setdefault(ticker, []).append({"high": high, "low": low, "close": close})
            prev = prev_closes.get(ticker)
            if prev is not None and prev > 0:
                pct = (close - prev) / prev
                for window in ("1m", "5m", "15m", "1h", "1d"):
                    snapshot[f"pct_change:{ticker}:{window}"] = pct
            for leaf in leaves:
                if leaf.get("ticker") != ticker or leaf["metric"] not in INDICATOR_METRICS:
                    continue
                resolved = resolved_params(leaf)
                key = leaf_key({**leaf, "params": resolved})
                snapshot[key] = ind.indicator_value(
                    leaf["metric"],
                    resolved,
                    closes=closes_hist[ticker],
                    bars=bars_hist[ticker],
                    last=close,
                    today_open=op_price,
                    prev_close=prev,
                )
            prev_closes[ticker] = close

        # crossing support: populate _prior: keys from the previous bar's values
        for k, _v in list(snapshot.items()):
            snapshot[f"_prior:{k}"] = prev_values.get(k)

        matched, values = evaluate_condition(condition, snapshot)
        if matched:
            # Compute forward-return scores (look-ahead; intentional for signal evaluation)
            fwd_1d = trading_day_forward_return_pct(score_ticker, ts, 24)
            fwd_5d = trading_day_forward_return_pct(score_ticker, ts, 120)
            matches.append(
                BacktestMatch(ts=ts, values=values, fwd_1d_pct=fwd_1d, fwd_5d_pct=fwd_5d)
            )

        prev_values.update({k: v for k, v in snapshot.items() if not k.startswith("_prior:")})

    return matches


def backtest_summary(matches: list[BacktestMatch]) -> dict:
    """Compute aggregate signal-quality stats from a list of :class:`BacktestMatch`.

    Returns a dict with:
    - ``matches``: total count of matched bars
    - ``scored_1d``: count of matches with a non-None fwd_1d_pct
    - ``avg_fwd_1d_pct``: mean forward 1-day return among scored matches (None if none scored)
    - ``hit_rate_1d``: fraction of scored_1d matches with positive fwd_1d_pct (None if none scored)
    - ``scored_5d``: count of matches with a non-None fwd_5d_pct
    - ``avg_fwd_5d_pct``: mean forward 5-day return among scored matches (None if none scored)
    - ``hit_rate_5d``: fraction of scored_5d matches with positive fwd_5d_pct (None if none scored)

    Hit-rate is rounded to 4 decimal places for stable serialization.
    """
    scored_1d = [m.fwd_1d_pct for m in matches if m.fwd_1d_pct is not None]
    scored_5d = [m.fwd_5d_pct for m in matches if m.fwd_5d_pct is not None]

    avg_1d = round(mean(scored_1d), 4) if scored_1d else None
    avg_5d = round(mean(scored_5d), 4) if scored_5d else None
    hit_1d = round(sum(1 for v in scored_1d if v > 0) / len(scored_1d), 4) if scored_1d else None
    hit_5d = round(sum(1 for v in scored_5d if v > 0) / len(scored_5d), 4) if scored_5d else None

    return {
        "matches": len(matches),
        "scored_1d": len(scored_1d),
        "avg_fwd_1d_pct": avg_1d,
        "hit_rate_1d": hit_1d,
        "scored_5d": len(scored_5d),
        "avg_fwd_5d_pct": avg_5d,
        "hit_rate_5d": hit_5d,
    }


def _unique_tickers(condition: dict) -> set[str]:
    return {
        leaf["ticker"]
        for leaf in iter_leaves(condition)
        if isinstance(leaf.get("ticker"), str) and leaf["ticker"]
    }
