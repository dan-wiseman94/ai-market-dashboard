"""Rung 1 — providers + profiles.

Three ProviderConfig rows (claude, openai, local) and two TradingProfile
rows (E2E Default, E2E Tools-Enabled with tools/thinking/memory enabled).

Idempotent — safe to call repeatedly.
"""

from __future__ import annotations

from decimal import Decimal


def seed_minimal() -> None:
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig

    for provider, model in (
        ("claude", "claude-sonnet-4-6"),
        ("openai", "gpt-5-mini"),
        ("local", "local-7b"),
    ):
        ProviderConfig.objects.update_or_create(
            provider=provider,
            defaults={
                "base_url": ("http://localhost:11434/v1" if provider == "local" else ""),
                "default_model": model,
                "enabled": True,
                "daily_cost_cap_usd": Decimal("100.00"),
                "monthly_cost_cap_usd": Decimal("1000.00"),
            },
        )

    TradingProfile.objects.update_or_create(
        name="E2E Default",
        defaults={
            "style": "E2E test profile — observational trading style.",
            "default_provider": "claude",
            "default_model": "claude-sonnet-4-6",
            "active": True,
        },
    )
    TradingProfile.objects.update_or_create(
        name="E2E Tools-Enabled",
        defaults={
            "style": "E2E profile with tools + thinking + memory enabled.",
            "default_provider": "claude",
            "default_model": "claude-sonnet-4-6",
            "enable_tools": True,
            "enable_thinking": True,
            "thinking_budget": 2048,
            "enable_memory": True,
            "active": False,
        },
    )
