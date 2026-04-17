"""Cost aggregation helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from django.db.models import Count, Sum

from apps.threads.models import AIRun


def cost_breakdown_today() -> dict:
    start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    qs = AIRun.objects.filter(created_at__gte=start)
    by_provider = list(
        qs.values("provider").annotate(
            cost_usd=Sum("cost_usd"),
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cached_tokens=Sum("cached_tokens"),
            runs=Count("id"),
        ).order_by("provider")
    )
    total = sum((row["cost_usd"] or Decimal("0")) for row in by_provider)
    return {
        "total_usd": total or Decimal("0"),
        "by_provider": [
            {
                "provider": row["provider"],
                "cost_usd": row["cost_usd"] or Decimal("0"),
                "input_tokens": row["input_tokens"] or 0,
                "output_tokens": row["output_tokens"] or 0,
                "cached_tokens": row["cached_tokens"] or 0,
                "runs": row["runs"],
            }
            for row in by_provider
        ],
    }
