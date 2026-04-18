"""Observer run timeline.

Bins Messages on observer-kind Threads per-day inside the window:
  success = role=assistant, status=done
  failed  = role=assistant, status=failed
  skipped = role=system, status=done   # observer writes these on cost-cap skip
Gaps are zero-filled so the UI can draw a clean bar chart without reshaping.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate

from apps.threads.models import Message


def observer_timeline(*, start: datetime, end: datetime) -> list[dict]:
    qs = Message.objects.filter(
        thread__kind="observer",
        created_at__gte=start, created_at__lt=end,
    )
    rows = list(
        qs.annotate(d=TruncDate("created_at"))
        .values("d", "role", "status")
        .annotate(n=Count("id"))
    )
    by_date: dict[str, dict] = {}
    for r in rows:
        d = r["d"].isoformat()
        bucket = by_date.setdefault(d, {"date": d, "success": 0, "failed": 0, "skipped": 0})
        role, status, n = r["role"], r["status"], r["n"]
        if role == "assistant" and status == "done":
            bucket["success"] += n
        elif role == "assistant" and status == "failed":
            bucket["failed"] += n
        elif role == "system":
            bucket["skipped"] += n
    out: list[dict] = []
    cur = start.date()
    last = end.date()
    while cur < last:
        key = cur.isoformat()
        out.append(by_date.get(key, {"date": key, "success": 0, "failed": 0, "skipped": 0}))
        cur += timedelta(days=1)
    return out
