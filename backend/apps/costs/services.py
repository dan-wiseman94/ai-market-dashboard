from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from apps.threads.models import AIRun

# Shared per-(provider/model) token + cost aggregation applied across the breakdowns.
_TOKEN_AGG = {
    "cost_usd": Sum("cost_usd"),
    "runs": Count("id"),
    "input_tokens": Sum("input_tokens"),
    "output_tokens": Sum("output_tokens"),
    "cached_tokens": Sum("cached_tokens"),
}


def cost_breakdown_today() -> dict:
    """Legacy shape for the existing /api/costs/today/ endpoint. Kept for back-compat."""
    start = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    by_provider = _provider_breakdown(start=start)
    return {
        "total_usd": sum((row["cost_usd"] for row in by_provider), Decimal("0")),
        "by_provider": by_provider,
    }


def summary(*, start: datetime, end: datetime) -> dict:
    """Rich summary used by the new /api/costs/summary/ endpoint.

    Returns:
      {
        total: Decimal,
        by_provider: [{provider, cost_usd, runs, input_tokens, output_tokens, cached_tokens}],
        by_model: [{provider, model, ...}],
        by_thread: [{thread_id, title, cost_usd, runs}],
        daily: [{date, cost_usd, runs}],   # zero-filled gaps
      }
    """
    qs = AIRun.objects.filter(created_at__gte=start, created_at__lt=end)
    by_provider = list(qs.values("provider").annotate(**_TOKEN_AGG).order_by("-cost_usd"))
    by_model = list(qs.values("provider", "model").annotate(**_TOKEN_AGG).order_by("-cost_usd"))
    by_thread = list(
        qs.values("message__thread_id", "message__thread__title")
        .annotate(cost_usd=Sum("cost_usd"), runs=Count("id"))
        .order_by("-cost_usd")[:10]
    )
    by_thread = [
        {
            "thread_id": r["message__thread_id"],
            "title": r["message__thread__title"],
            "cost_usd": r["cost_usd"],
            "runs": r["runs"],
        }
        for r in by_thread
    ]

    daily_rows = list(
        qs.annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(cost_usd=Sum("cost_usd"), runs=Count("id"))
        .order_by("d")
    )
    daily = _fill_daily_gaps(daily_rows, start.date(), end.date())

    total = sum((row["cost_usd"] for row in by_provider), Decimal("0"))
    return {
        "total": total,
        "by_provider": by_provider,
        "by_model": by_model,
        "by_thread": by_thread,
        "daily": daily,
    }


def _fill_daily_gaps(rows: list[dict], start: date, end: date) -> list[dict]:
    by_date = {r["d"]: r for r in rows}
    out: list[dict] = []
    cur = start
    while cur <= end:
        r = by_date.get(cur)
        out.append(
            {
                "date": cur.isoformat(),
                "cost_usd": (r["cost_usd"] if r else Decimal("0")) or Decimal("0"),
                "runs": r["runs"] if r else 0,
            }
        )
        cur += timedelta(days=1)
    return out


def _provider_breakdown(*, start: datetime, end: datetime | None = None) -> list[dict]:
    qs = AIRun.objects.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    return [
        {
            "provider": row["provider"],
            "cost_usd": row["cost_usd"] or Decimal("0"),
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "cached_tokens": row["cached_tokens"] or 0,
            "runs": row["runs"],
        }
        for row in qs.values("provider").annotate(**_TOKEN_AGG).order_by("provider")
    ]


def caps() -> list[dict]:
    """Per-provider daily + monthly cap progress. Monthly is None if not configured.

    Monthly uses the same rolling-30-day window as `ai.cost.monthly_spend_usd`
    so UI progress matches what enforcement actually gates on.
    """
    from apps.secrets.models import ProviderConfig

    now = datetime.now(tz=UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_window_start = now - timedelta(days=30)

    out: list[dict] = []
    for pc in ProviderConfig.objects.all():
        day_spent = (
            AIRun.objects.filter(
                provider=pc.provider,
                created_at__gte=day_start,
            ).aggregate(s=Sum("cost_usd"))["s"]
        ) or Decimal("0")

        daily = {
            "cap": pc.daily_cost_cap_usd,
            "spent": day_spent,
            "pct": min(1.0, float(day_spent / pc.daily_cost_cap_usd))
            if pc.daily_cost_cap_usd
            else 0.0,
        }

        monthly = None
        if pc.monthly_cost_cap_usd is not None:
            month_spent = (
                AIRun.objects.filter(
                    provider=pc.provider,
                    created_at__gte=month_window_start,
                ).aggregate(s=Sum("cost_usd"))["s"]
            ) or Decimal("0")
            monthly = {
                "cap": pc.monthly_cost_cap_usd,
                "spent": month_spent,
                "pct": min(1.0, float(month_spent / pc.monthly_cost_cap_usd)),
            }

        out.append({"provider": pc.provider, "daily": daily, "monthly": monthly})
    return out


def snapshot_breakdown(snapshot_id: int) -> list[dict]:
    """Per-section token attribution + proportional cost share.

    Attribution is proportional-to-tokens, not per-API-call. Sections themselves
    only cost data-provider API calls (free under our current setup); the AI
    summary is the monetized call. We split that cost by each section's share
    of the payload tokens that went into the summary.
    """
    from apps.snapshots.models import SnapshotSection

    sections = list(SnapshotSection.objects.filter(snapshot_id=snapshot_id).order_by("kind"))
    total_tokens = sum(s.payload_tokens for s in sections) or 1

    # Find the single AIRun that consumed this snapshot (pinned_snapshot_id on Thread).
    ai_run = (
        AIRun.objects.filter(message__thread__pinned_snapshot_id=snapshot_id, status="done")
        .order_by("-created_at")
        .first()
    )
    total_cost = ai_run.cost_usd if ai_run else Decimal("0")

    out: list[dict] = []
    for sec in sections:
        share = (
            (Decimal(sec.payload_tokens) / Decimal(total_tokens)) if total_tokens else Decimal("0")
        )
        cost_share = (total_cost * share).quantize(Decimal("0.0001"))
        out.append(
            {
                "section": sec.kind,
                "payload_tokens": sec.payload_tokens,
                "cost_share_usd": cost_share,
            }
        )
    return out


def csv_rows(*, start: datetime, end: datetime) -> Iterator[list[str]]:
    """Yield header + one row per AIRun, for StreamingHttpResponse."""
    yield [
        "created_at",
        "provider",
        "model",
        "thread_id",
        "snapshot_id",
        "tokens_in",
        "tokens_out",
        "tokens_cached",
        "cost_usd",
        "duration_ms",
    ]
    qs = (
        AIRun.objects.filter(created_at__gte=start, created_at__lt=end)
        .select_related("message__thread")
        .order_by("created_at")
    )
    for r in qs.iterator(chunk_size=500):
        yield [
            r.created_at.isoformat(),
            r.provider,
            r.model,
            str(r.message.thread_id),
            str(r.message.thread.pinned_snapshot_id or ""),
            str(r.input_tokens),
            str(r.output_tokens),
            str(r.cached_tokens),
            str(r.cost_usd),
            str(r.latency_ms),
        ]
