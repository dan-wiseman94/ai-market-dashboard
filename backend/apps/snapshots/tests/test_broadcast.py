from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_capture_broadcasts_section_events():
    p = TradingProfile.objects.create(name="P", style="x")
    events = []

    def collect(snapshot_id, msg):
        events.append((snapshot_id, msg))

    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 1}}),
        patch("apps.snapshots.services.fetch_positions", side_effect=RuntimeError("x")),
        patch("apps.snapshots.services._broadcast", side_effect=collect),
    ):
        capture(
            profile=p,
            objective="",
            includes=["quotes", "positions"],
            source="manual",
            watchlist_tickers=["SPY"],
        )

    kinds = [msg["event"] for _, msg in events]
    assert "section_started" in kinds
    assert "section_done" in kinds
    assert "section_failed" in kinds
    assert "ready" in kinds
