import pytest
from freezegun import freeze_time

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.services import _build_market_state, capture_for_existing


@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_build_market_state_union():
    st = _build_market_state(["BTC-USD", "SPY"])
    assert st["any_open"] is True  # crypto open
    assert st["markets"]["crypto"]["is_open"] is True
    assert st["markets"]["us_equity"]["is_open"] is False
    assert "BTC-USD" in st["representative_tickers"]


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")
def test_capture_stamps_market_state():
    profile = TradingProfile.objects.create(name="t", style="s")
    snap = Snapshot.objects.create(profile=profile, includes=[], status="pending")
    capture_for_existing(snap, watchlist_tickers=["BTC-USD"])
    snap.refresh_from_db()
    assert snap.market_state is not None
    assert "crypto" in snap.market_state["markets"]
