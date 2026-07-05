"""Staged client-capture screenshots must reach the AI.

A client-uploaded screenshot is FK-attached to a Snapshot (SnapshotViewSet.create)
but does not enter the image section's payload["image_ids"] on its own — the only
thing the AI-delivery path (_snapshot_image_ids) reads. Without the merge,
server-rendered charts would be delivered while user screenshots were silently
dropped. The design delivers client captures + server renders both.
"""

from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.services import capture_for_existing
from apps.threads._request import _snapshot_image_ids

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _fake_render(ticker, timeframe, bars, *, snapshot_id):
    return SnapshotImage.objects.create(
        snapshot_id=snapshot_id,
        kind="server_render",
        data=PNG,
        caption=f"{ticker} {timeframe}, {bars} bars",
    )


def _stage_client_capture(snap, caption="my screenshot"):
    """Mirror SnapshotViewSet.create attaching a staged upload via the FK only."""
    return SnapshotImage.objects.create(
        snapshot=snap, kind="client_capture", data=PNG, caption=caption
    )


@pytest.mark.django_db
def test_client_capture_delivered_alongside_server_render():
    """`image` in includes: section payload carries BOTH the server render and
    the staged client capture, and the delivery seam returns both."""
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["image"], status="pending")
    client = _stage_client_capture(snap)

    with patch("apps.snapshots.services.render_chart_png", side_effect=_fake_render):
        capture_for_existing(snap, watchlist_tickers=["SPY"], ohlc_ticker="SPY")

    section = snap.sections.get(kind="image")
    assert section.status == "done"
    ids = section.payload["image_ids"]
    assert client.id in ids, "client capture missing from image section payload"
    assert len(ids) == 2, "expected server render + client capture"
    assert client.id in _snapshot_image_ids(snap.id)


@pytest.mark.django_db
def test_client_capture_delivered_when_image_not_in_includes():
    """`image` NOT in includes (the composer default): the staged client capture
    still gets its own `image` section so it reaches the AI, and the snapshot is
    ready (it carries deliverable data)."""
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=[], status="pending")
    client = _stage_client_capture(snap)

    capture_for_existing(snap, watchlist_tickers=["SPY"])

    section = snap.sections.get(kind="image")
    assert section.status == "done"
    assert section.payload["image_ids"] == [client.id]
    assert _snapshot_image_ids(snap.id) == [client.id]
    snap.refresh_from_db()
    assert snap.status == "ready"
