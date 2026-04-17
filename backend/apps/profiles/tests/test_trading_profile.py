import pytest

from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_create_profile_with_defaults():
    p = TradingProfile.objects.create(
        name="0DTE scalps",
        style="Fast SPY scalps. 1-5 min holds. VWAP reclaims.",
    )
    assert p.active is True
    assert p.default_includes == ["quotes", "positions", "breadth"]
    assert p.default_provider == "claude"
    assert p.default_model == "claude-sonnet-4-6"


@pytest.mark.django_db
def test_profile_stores_custom_includes():
    p = TradingProfile.objects.create(
        name="Swings",
        style="Multi-day swings.",
        default_includes=["quotes", "ohlc", "positions", "notes"],
        default_model="claude-opus-4-7",
    )
    p.refresh_from_db()
    assert p.default_includes == ["quotes", "ohlc", "positions", "notes"]
    assert p.default_model == "claude-opus-4-7"


@pytest.mark.django_db
def test_profile_name_unique():
    TradingProfile.objects.create(name="A", style="x")
    with pytest.raises(Exception):
        TradingProfile.objects.create(name="A", style="y")
