from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.profiles.models import TradingProfile
from apps.threads.coach import build_system_prompt

NOW = datetime(2026, 5, 29, 14, 30, tzinfo=UTC)


@pytest.mark.django_db
def test_system_prompt_wraps_style_and_includes_date_when_enabled():
    p = TradingProfile.objects.create(name="p", style="Aggressive intraday")
    out = build_system_prompt(p, now=NOW)
    assert "Aggressive intraday" in out
    assert "observational" in out.lower()
    assert "2026-05-29" in out


@pytest.mark.django_db
def test_system_prompt_is_legacy_style_only_when_disabled():
    p = TradingProfile.objects.create(name="p", style="Aggressive intraday", enable_coach=False)
    assert build_system_prompt(p, now=NOW) == "Aggressive intraday"


def test_system_prompt_none_profile_is_empty():
    assert build_system_prompt(None, now=NOW) == ""
