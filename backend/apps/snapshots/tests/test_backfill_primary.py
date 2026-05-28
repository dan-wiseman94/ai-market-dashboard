import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.mark.django_db
def test_backfill_populates_from_quotes():
    from apps.snapshots.migrations import _backfill  # helper module (Step 3)

    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    snap = Snapshot.objects.create(
        profile=p, includes=["quotes"], status="ready", primary_ticker=None
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"meta": {"last": 1}}
    )
    _backfill.populate(Snapshot, SnapshotSection)
    snap.refresh_from_db()
    assert snap.primary_ticker == "META"
