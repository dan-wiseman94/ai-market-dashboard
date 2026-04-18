"""Idempotent minimal seed: 1 provider config, 1 profile."""
from __future__ import annotations

from decimal import Decimal


def seed_minimal() -> None:
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.update_or_create(
        provider="claude",
        defaults={
            "base_url": "",
            "default_model": "claude-sonnet-4-6",
            "enabled": True,
            "daily_cost_cap_usd": Decimal("100.00"),
        },
    )
    # TradingProfile has: name (unique), style (TextField, required non-blank),
    # default_includes (JSONField default=list), default_provider, default_model, active.
    TradingProfile.objects.update_or_create(
        name="E2E Default",
        defaults={
            "style": "E2E test profile — observational trading style.",
            "default_provider": "claude",
            "default_model": "claude-sonnet-4-6",
        },
    )
