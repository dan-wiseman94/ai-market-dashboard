"""A non-integer id on the snapshot diff action must 404, not 500.

`GET /api/snapshots/null/diff/` (schemathesis fuzzes this) must use DRF's
get_object_or_404, which maps the PK-cast ValueError to 404. Django's
get_object_or_404 catches only DoesNotExist, so on `id=<non-int>` it would
let the ValueError escape as a 500.
"""

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


@pytest.mark.django_db
def test_diff_non_integer_pk_returns_404_not_500():
    r = APIClient().get("/api/snapshots/null/diff/")
    assert r.status_code == 404


@pytest.mark.django_db
def test_diff_non_integer_against_returns_404_not_500():
    profile = TradingProfile.objects.create(name="diff-badid", default_includes=["quotes"])
    snap = Snapshot.objects.create(
        profile=profile, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    r = APIClient().get(f"/api/snapshots/{snap.id}/diff/?against=null")
    assert r.status_code == 404
