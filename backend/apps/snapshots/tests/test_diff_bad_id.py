"""Regression: the snapshot diff action 500'd on a non-integer id.

schemathesis fuzzing hit `GET /api/snapshots/null/diff/` → 500, because the view
used Django's get_object_or_404 (catches only DoesNotExist) on `id=<non-int>`,
letting the PK-cast ValueError escape. DRF's get_object_or_404 maps it to 404.
"""

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot


@pytest.mark.django_db
def test_diff_non_integer_pk_returns_404_not_500():
    r = APIClient().get("/api/snapshots/null/diff/")
    assert r.status_code == 404  # was 500


@pytest.mark.django_db
def test_diff_non_integer_against_returns_404_not_500():
    profile = TradingProfile.objects.create(name="diff-badid", default_includes=["quotes"])
    snap = Snapshot.objects.create(
        profile=profile, includes=["quotes"], status="ready", primary_ticker="NVDA"
    )
    r = APIClient().get(f"/api/snapshots/{snap.id}/diff/?against=null")
    assert r.status_code == 404  # was 500
