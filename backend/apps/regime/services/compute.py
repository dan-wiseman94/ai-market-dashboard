from __future__ import annotations

from apps.regime.models import RegimeReading


def current_regime() -> RegimeReading | None:
    """The latest reading, or None when no reading has been produced yet."""
    return RegimeReading.objects.order_by("-created_at").first()
