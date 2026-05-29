import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.services import capture_for_existing


@pytest.mark.django_db
def test_capture_sets_primary_ticker(monkeypatch):
    import apps.snapshots.services as svc

    monkeypatch.setitem(
        svc._FETCHERS, "quotes", lambda **_: {"data": {"tsla": {"last": 5}, "spy": {"last": 1}}}
    )
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(profile=p, includes=["quotes"], status="pending")
    capture_for_existing(snap, watchlist_tickers=["TSLA", "SPY"])
    snap.refresh_from_db()
    assert snap.primary_ticker == "TSLA"


@pytest.mark.django_db
def test_capture_no_quotes_leaves_primary_null(monkeypatch):
    import apps.snapshots.services as svc

    monkeypatch.setitem(svc._FETCHERS, "notes", lambda **_: {"data": {}})
    p = TradingProfile.objects.create(name="P", default_includes=["notes"])
    snap = Snapshot.objects.create(profile=p, includes=["notes"], status="pending")
    capture_for_existing(snap)
    snap.refresh_from_db()
    assert snap.primary_ticker is None
