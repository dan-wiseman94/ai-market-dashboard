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
        market_state={"any_open": True, "markets": {"us_equity": {"is_open": True}}},
    )
    out = serialize_for_ai(snap, provider="claude", model="")
    assert "Market state" not in out
