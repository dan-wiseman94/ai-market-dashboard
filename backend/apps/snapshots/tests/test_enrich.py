from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.services.enrich import enrich_snapshot


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s")


def _snap(profile, *, includes, primary="NVDA") -> Snapshot:
    return Snapshot.objects.create(
        profile=profile, status="ready", includes=includes, source="manual", primary_ticker=primary
    )


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.iv_summary")
@patch("apps.snapshots.services.enrich.relative_strength")
@patch("apps.snapshots.services.enrich.sector_rotation")
def test_enrich_writes_gated_parts(mock_rot, mock_rs, mock_iv, profile):
    mock_rot.return_value = {"ranked": [{"etf": "XLK", "sector": "Technology", "pct": 1.0}]}
    mock_rs.return_value = {"ticker": "NVDA", "benchmark": "SPY", "windows": []}
    mock_iv.return_value = {"ticker": "NVDA", "atm_iv": 0.5}

    snap = _snap(profile, includes=["quotes", "breadth", "chain"])
    enrich_snapshot(snap)

    sec = SnapshotSection.objects.get(snapshot=snap, kind="intel")
    assert sec.status == "done"
    assert set(sec.payload) == {"rotation", "relative_strength", "iv"}


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.iv_summary")
@patch("apps.snapshots.services.enrich.relative_strength")
@patch("apps.snapshots.services.enrich.sector_rotation")
def test_enrich_positions_only_writes_no_section(mock_rot, mock_rs, mock_iv, profile):
    snap = _snap(profile, includes=["positions"], primary=None)
    enrich_snapshot(snap)
    assert not SnapshotSection.objects.filter(snapshot=snap, kind="intel").exists()
    mock_rot.assert_not_called()
    mock_rs.assert_not_called()
    mock_iv.assert_not_called()


@pytest.mark.django_db
@patch("apps.snapshots.services.enrich.relative_strength", side_effect=RuntimeError("boom"))
@patch("apps.snapshots.services.enrich.sector_rotation")
def test_enrich_never_raises_and_keeps_healthy_parts(mock_rot, mock_rs, profile):
    mock_rot.return_value = {"ranked": [{"etf": "XLK", "sector": "Technology", "pct": 1.0}]}
    snap = _snap(profile, includes=["quotes", "breadth"])
    enrich_snapshot(snap)
    sec = SnapshotSection.objects.get(snapshot=snap, kind="intel")
    assert set(sec.payload) == {"rotation"}
