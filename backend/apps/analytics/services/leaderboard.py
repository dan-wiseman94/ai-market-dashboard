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

Forward returns use trading-day horizons on the ticker's market calendar
(see apps.market.returns.trading_day_forward_return_pct): forward_hours is
reinterpreted as trading sessions, and a missing bar is an honest coverage
gap (None) rather than a stale fill.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db.models import Avg, Count, Sum

from apps.market.returns import trading_day_forward_return_pct
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

    # Per (provider, model): the list of computable forward returns. A key only
    # gains an entry when a run actually prices out; the row loop below falls back
    # to an empty list (coverage 0, avg None) for keys that never did.
    returns: dict[tuple[str, str], list[float]] = {}
    for run in qs.select_related("message__thread__pinned_snapshot").iterator():
        snap = run.message.thread.pinned_snapshot
        if snap is None:
            continue
        primary = _primary_ticker(snap)
        if primary is None:
            continue
        ret = trading_day_forward_return_pct(primary, run.created_at, forward_hours)
        if ret is None:
            continue
        returns.setdefault((run.provider, run.model), []).append(ret)

    rows: list[dict] = []
    for r in agg:
        key = (r["provider"], r["model"])
        rs = returns.get(key, [])  # one entry per run that priced out
        runs = r["runs"]
        coverage = (len(rs) / runs * 100.0) if runs else 0.0
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
