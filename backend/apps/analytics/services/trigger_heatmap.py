"""Trigger-fire heatmap: 7 × 24 grid of counts by (weekday, hour)."""
from __future__ import annotations

from datetime import datetime

from apps.triggers.models import TriggerFiring


def trigger_heatmap(*, start: datetime, end: datetime) -> list[dict]:
    counts: dict[tuple[int, int], int] = {
        (d, h): 0 for d in range(7) for h in range(24)
    }
    qs = TriggerFiring.objects.filter(
        fired_at__gte=start, fired_at__lt=end,
    ).values_list("fired_at", flat=True)
    for ts in qs:
        key = (ts.weekday(), ts.hour)
        counts[key] = counts.get(key, 0) + 1
    return [
        {"weekday": d, "hour": h, "count": counts[(d, h)]}
        for d in range(7) for h in range(24)
    ]
