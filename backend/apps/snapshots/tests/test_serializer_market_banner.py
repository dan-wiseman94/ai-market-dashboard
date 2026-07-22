import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.serializer import serialize_for_ai


@pytest.mark.django_db
def test_banner_present_when_market_closed():
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(
        profile=profile,
        includes=[],
        status="ready",
        market_state={"any_open": False, "markets": {"us_equity": {"is_open": False}}},
    )
    out = serialize_for_ai(snap, provider="claude", model="")
    assert "Market state" in out
    assert "us_equity" in out


@pytest.mark.django_db
def test_no_banner_when_open():
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(
        profile=profile,
        includes=[],
        status="ready",
        market_state={
            "any_open": True,
            "markets": {"us_equity": {"is_open": True, "phase": "open"}},
        },
    )
    out = serialize_for_ai(snap, provider="claude", model="")
    assert "Market state" not in out


@pytest.mark.django_db
def test_premarket_phase_banner_flags_incomplete_day_fields():
    # The audit's pre-open snapshot fed zeroed day-high/low and warm-up breadth
    # internals with no caveat — futures open kept any_open True, so the closed
    # banner never fired. The phase banner covers exactly that gap.
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(
        profile=profile,
        includes=[],
        status="ready",
        market_state={
            "any_open": True,  # e.g. CME futures open while equities are premarket
            "markets": {
                "us_equity": {"is_open": False, "phase": "premarket"},
                "cme_futures": {"is_open": True, "phase": "open"},
            },
        },
    )
    out = serialize_for_ai(snap, provider="claude", model="")
    assert "premarket" in out
    assert "day high/low" in out
