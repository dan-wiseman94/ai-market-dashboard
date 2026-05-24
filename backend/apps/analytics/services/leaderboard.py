"""Provider prediction leaderboard.

For each (provider, model) pair in the given window, report:
- runs, total_cost_usd, avg_latency_ms (cheap aggregates from AIRun)
- avg_forward_return_pct: per-run % change of the snapshot's primary
  ticker between capture time and capture+forward_hours, averaged.
- coverage_pct: share of runs where forward return was computable
  (snapshot had a `quotes` section + we have an OHLC bar at both
  endpoints).

We pick the "primary ticker" of a snapshot as the first key of the
first `quotes` section. This is a best-effort proxy; runs without a
snapshot or without usable price history show coverage=0.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum

from apps.market.models import OHLCBar
from apps.threads.models import AIRun


def provider_leaderboard(
    *,
    start: datetime,
    end: datetime,
    forward_hours: int = 24,
) -> list[dict]:
    qs = AIRun.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        status="done",
    )
    agg = (
        qs.values("provider", "model")
        .annotate(
            runs=Count("id"),
            total_cost_usd=Sum("cost_usd"),
            avg_latency_ms=Avg("latency_ms"),
        )
        .order_by("-total_cost_usd")
    )

    returns: dict[tuple[str, str], list[float]] = {}
    priced: dict[tuple[str, str], int] = {}
    for run in qs.select_related("message__thread__pinned_snapshot").iterator():
        key = (run.provider, run.model)
        returns.setdefault(key, [])
        priced.setdefault(key, 0)
        snap = run.message.thread.pinned_snapshot
        if snap is None:
            continue
        primary = _primary_ticker(snap)
        if primary is None:
            continue
        ret = _forward_return_pct(primary, run.created_at, forward_hours)
        if ret is None:
            continue
        returns[key].append(ret)
        priced[key] += 1

    rows: list[dict] = []
    for r in agg:
        key = (r["provider"], r["model"])
        rs = returns.get(key, [])
        runs = r["runs"]
        coverage = (priced.get(key, 0) / runs * 100.0) if runs else 0.0
        avg_ret = (sum(rs) / len(rs)) if rs else None
        rows.append(
            {
                "provider": r["provider"],
                "model": r["model"],
                "runs": runs,
                "total_cost_usd": r["total_cost_usd"] or Decimal("0"),
                "avg_latency_ms": int(r["avg_latency_ms"] or 0),
                "avg_forward_return_pct": avg_ret,
                "coverage_pct": coverage,
            }
        )
    return rows


def _primary_ticker(snap) -> str | None:
    for sec in snap.sections.all():
        if sec.kind == "quotes" and isinstance(sec.payload, dict):
            for key in sec.payload:
                return str(key)
    return None


def _forward_return_pct(
    ticker: str,
    at: datetime,
    forward_hours: int,
) -> float | None:
    """Closest 1h bar at `at` and at `at + forward_hours`, in percent."""
    target_end = at + timedelta(hours=forward_hours)
    t0 = _nearest_bar_close(ticker, at)
    t1 = _nearest_bar_close(ticker, target_end)
    if t0 is None or t1 is None or t0 == 0:
        return None
    return (t1 - t0) / t0 * 100.0


def _nearest_bar_close(ticker: str, at: datetime) -> float | None:
    bar = (
        OHLCBar.objects.filter(ticker=ticker, ts__lte=at + timedelta(hours=1))
        .only("close")
        .order_by("-ts")
        .first()
    )
    if bar is None:
        return None
    return float(bar.close)
