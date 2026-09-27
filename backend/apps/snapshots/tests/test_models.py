import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


@pytest.mark.django_db
def test_fed_and_flowlite_are_valid_section_kind_choices():
    kind_map = dict(SnapshotSection.KIND_CHOICES)
    assert "fed" in kind_map
    assert "flowlite" in kind_map
    assert len("fed") <= 16
    assert len("flowlite") <= 16

    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["fed", "flowlite"], source="manual")
    SnapshotSection.objects.create(snapshot=s, kind="fed", payload={}, status="done")
    SnapshotSection.objects.create(snapshot=s, kind="flowlite", payload={}, status="done")
    assert s.sections.count() == 2
