import pytest

from apps.observer.models import EventTrigger
from apps.observer.triggers.services.thesis_guard import build_guard_condition, sync_thesis_guard
from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis


@pytest.mark.django_db
def test_build_condition_bullish():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(
        title="t",
        ticker="NVDA",
        direction="bullish",
        profile=p,
        target_price=200,
        invalidation_price=150,
    )
    cond = build_guard_condition(th)
    assert cond is not None
    # Bullish: the target fires on an upside cross, the invalidation on a downside cross.
    assert {(leaf["op"], leaf["value"]) for leaf in cond["any"]} == {
        ("crosses_above", 200.0),
        ("crosses_below", 150.0),
    }


@pytest.mark.django_db
def test_build_condition_none_without_prices():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(title="t", ticker="NVDA", direction="bullish", profile=p)
    assert build_guard_condition(th) is None


@pytest.mark.django_db
def test_sync_creates_and_removes_guard():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(
        title="t",
        ticker="NVDA",
        direction="bullish",
        profile=p,
        target_price=200,
        invalidation_price=150,
        guard_enabled=True,
    )
    g = sync_thesis_guard(th)
    assert g is not None and g.source_thesis_id == th.id and g.enabled
    th.guard_enabled = False
    th.save()
    sync_thesis_guard(th)
    assert not EventTrigger.objects.get(source_thesis=th).enabled  # disabled, not orphaned


@pytest.mark.django_db
def test_sync_disables_on_close():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(
        title="t",
        ticker="NVDA",
        direction="bullish",
        profile=p,
        target_price=200,
        invalidation_price=150,
        guard_enabled=True,
    )
    sync_thesis_guard(th)
    th.status = "closed_win"
    th.save()
    sync_thesis_guard(th)
    assert not EventTrigger.objects.get(source_thesis=th).enabled
