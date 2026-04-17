"""Server-side chart rendering via Playwright. Real impl in Task 26."""
from __future__ import annotations

from apps.snapshots.models import SnapshotImage


def render_chart_png(ticker: str, timeframe: str, bars: int, *, snapshot_id: int) -> SnapshotImage:
    raise NotImplementedError("Playwright render arrives in Task 26")
