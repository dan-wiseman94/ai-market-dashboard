from __future__ import annotations

from django.utils import timezone

from apps.desk import constants as C


def rank(candidates: list[dict]) -> list[dict]:
    """Highest severity first. ('How much you care' weighting is a v2 refinement.)"""
    return sorted(candidates, key=lambda c: c.get("severity", 0.0), reverse=True)


def in_cooldown(anomaly_type: str, ticker: str) -> bool:
    from apps.desk.models import DeskEntry

    cutoff = timezone.now() - timezone.timedelta(hours=C.COOLDOWN_HOURS)
    return DeskEntry.objects.filter(
        anomaly_type=anomaly_type, ticker=(ticker or ""), created_at__gte=cutoff
    ).exists()
