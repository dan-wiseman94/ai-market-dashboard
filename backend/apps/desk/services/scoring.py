from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.desk import constants as C


def rank(candidates: list[dict]) -> list[dict]:
    """Highest severity first. ('How much you care' weighting is a v2 refinement.)"""
    return sorted(candidates, key=lambda c: c.get("severity", 0.0), reverse=True)


def in_cooldown(anomaly_type: str, ticker: str) -> bool:
    from apps.desk.models import DeskEntry

    cutoff = timezone.now() - timedelta(hours=C.COOLDOWN_HOURS)
    return DeskEntry.objects.filter(
        anomaly_type=anomaly_type, ticker=(ticker or ""), created_at__gte=cutoff
    ).exists()


def originated_today() -> int:
    """How many DeskEntry rows were originated so far today (calendar day, active tz).

    Backs the per-day origination cap — a hard cost backstop on autonomous spend that
    resets at midnight, distinct from the per-(ticker, anomaly) cooldown window."""
    from apps.desk.models import DeskEntry

    return DeskEntry.objects.filter(created_at__date=timezone.localdate()).count()
