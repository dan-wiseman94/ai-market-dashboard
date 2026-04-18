import pytest
from apps.observer.models import ObserverSchedule
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_observer_schedule_persists_with_required_fields():
    p = TradingProfile.objects.create(name="Day Trader", style="x")
    s = ObserverSchedule.objects.create(
        name="every 15min during market hours",
        profile=p,
    )
    assert s.id is not None
    assert s.enabled is True
    assert s.market_hours_only is True
    assert s.objective_template == ""
    assert s.override_provider == ""
    assert s.override_model == ""
    assert s.default_includes == []
    assert s.default_watchlist_tickers == []
    assert s.periodic_task is None
    assert s.last_fired_at is None


@pytest.mark.django_db
def test_observer_schedule_carries_overrides_and_includes():
    p = TradingProfile.objects.create(name="Day Trader", style="x")
    s = ObserverSchedule.objects.create(
        name="cheap nightly summary", profile=p,
        objective_template="Summarize after-hours moves.",
        override_provider="openai", override_model="gpt-5-nano",
        default_includes=["quotes", "breadth"],
        default_watchlist_tickers=["SPY", "QQQ"],
    )
    assert s.objective_template == "Summarize after-hours moves."
    assert s.override_provider == "openai"
    assert s.override_model == "gpt-5-nano"
    assert s.default_includes == ["quotes", "breadth"]
    assert s.default_watchlist_tickers == ["SPY", "QQQ"]
