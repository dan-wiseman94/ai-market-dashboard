import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection


def _snap(p, last):
    s = Snapshot.objects.create(
        profile=p, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    SnapshotSection.objects.create(
        snapshot=s, kind="quotes", status="done", payload={"NVDA": {"last": last}}
    )
    return s


@pytest.mark.django_db
def test_diff_auto_selects_prior():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    a, b = _snap(p, 100), _snap(p, 110)
    r = APIClient().get(f"/api/snapshots/{b.id}/diff/")  # no ?against
    assert r.status_code == 200
    assert r.json()["prev_id"] == a.id and r.json()["curr_id"] == b.id


@pytest.mark.django_db
def test_diff_no_prior_returns_400():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    only = _snap(p, 100)
    r = APIClient().get(f"/api/snapshots/{only.id}/diff/")
    assert r.status_code == 400 and r.json()["code"] == "no_prior"
