import pytest
from django.db import IntegrityError

from apps.profiles.models import TradingProfile

NEW_DEFAULTS = ["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"]


@pytest.mark.django_db
def test_create_profile_with_defaults():
    p = TradingProfile.objects.create(
        name="0DTE scalps",
        style="Fast SPY scalps. 1-5 min holds. VWAP reclaims.",
    )
    assert p.active is True
    assert p.default_includes == NEW_DEFAULTS
    assert p.default_provider == "claude"
    assert p.default_model == "claude-sonnet-4-6"


@pytest.mark.django_db
def test_new_profile_seeds_rich_defaults():
    p = TradingProfile.objects.create(name="t", style="s")
    assert p.default_includes == NEW_DEFAULTS


@pytest.mark.django_db
def test_backfill_appends_missing_and_preserves_custom():
    from django.apps import apps as django_apps

    from apps.profiles.migrations import _backfill

    p = TradingProfile.objects.create(name="t2", style="s")
    TradingProfile.objects.filter(pk=p.pk).update(
        default_includes=["quotes", "notes", "chain"]  # user-trimmed + custom order
    )
    _backfill.add_kinds(django_apps, None)
    p.refresh_from_db()
    # Missing kinds append in KINDS order — positions/breadth land before ohlc.
    assert p.default_includes == [
        "quotes",
        "notes",
        "chain",
        "positions",
        "breadth",
        "ohlc",
        "news",
        "events",
        "macro",
    ]
    _backfill.add_kinds(django_apps, None)  # idempotent
    p.refresh_from_db()
    assert p.default_includes.count("chain") == 1


@pytest.mark.django_db
def test_profile_stores_custom_includes():
    p = TradingProfile.objects.create(
        name="Swings",
        style="Multi-day swings.",
        default_includes=["quotes", "ohlc", "positions", "notes"],
        default_model="claude-opus-4-8",
    )
    p.refresh_from_db()
    assert p.default_includes == ["quotes", "ohlc", "positions", "notes"]
    assert p.default_model == "claude-opus-4-8"


@pytest.mark.django_db
def test_profile_name_unique():
    TradingProfile.objects.create(name="A", style="x")
    with pytest.raises(IntegrityError):
        TradingProfile.objects.create(name="A", style="y")
