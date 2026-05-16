"""Seed is safe to call twice without duplicating rows."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_seed_minimal_is_idempotent() -> None:
    from apps.profiles.models import TradingProfile
    from apps.secrets.models import ProviderConfig

    from e2e.fixtures.seed_minimal import seed_minimal

    seed_minimal()
    c1 = ProviderConfig.objects.count()
    p1 = TradingProfile.objects.filter(name="E2E Default").count()

    seed_minimal()
    c2 = ProviderConfig.objects.count()
    p2 = TradingProfile.objects.filter(name="E2E Default").count()

    assert c1 == c2
    assert p1 == p2 == 1
