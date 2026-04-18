"""Each saved SnapshotSection has a populated payload_tokens field."""
from __future__ import annotations

import json

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.token_budget import estimate_tokens


@pytest.mark.django_db
def test_payload_tokens_matches_estimator() -> None:
    profile = TradingProfile.objects.create(name="test-profile", style="day trader")
    snap = Snapshot.objects.create(profile=profile)
    payload = {"hello": "world" * 50}
    section = SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", payload=payload, status="done",
    )
    expected = estimate_tokens(json.dumps(payload))
    from apps.snapshots.services import stamp_payload_tokens
    stamp_payload_tokens(section)
    section.refresh_from_db()
    assert section.payload_tokens == expected
    assert section.payload_tokens > 0
