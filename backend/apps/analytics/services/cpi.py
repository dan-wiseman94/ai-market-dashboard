"""Cost per insight.

insight count = (distinct threads that produced ≥1 done assistant message
                 via an AIRun in the window)
              + (distinct snapshots referenced by an AIRun's thread.pinned_snapshot)
              + (distinct trigger firings inside the window).

CPI = total AIRun cost / insight count. Returned as None when count is 0.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db.models import Sum

from apps.threads.models import AIRun
from apps.triggers.models import TriggerFiring


def cost_per_insight(*, start: datetime, end: datetime) -> dict:
    qs = AIRun.objects.filter(
        created_at__gte=start,
        created_at__lt=end,
        status="done",
    )
    total_cost = qs.aggregate(s=Sum("cost_usd"))["s"] or Decimal("0")

    threads = set(qs.values_list("message__thread_id", flat=True))
    snapshots = set(
        qs.exclude(message__thread__pinned_snapshot__isnull=True).values_list(
            "message__thread__pinned_snapshot_id", flat=True
        )
    )
    fires = TriggerFiring.objects.filter(
        fired_at__gte=start,
        fired_at__lt=end,
    ).count()

    insights = len(threads) + len(snapshots) + fires
    cpi = (total_cost / insights) if insights else None
    return {
        "total_cost_usd": total_cost,
        "threads_with_ai": len(threads),
        "snapshots_with_ai": len(snapshots),
        "trigger_fires": fires,
        "insights": insights,
        "cost_per_insight_usd": cpi,
    }
