"""Invariant guard: a SnapshotSection terminates at "done", never "ready".

CLAUDE.md landmine: only the parent ``Snapshot`` uses status="ready"; sections
terminate at "done" (``SnapshotSection.SECTION_STATUS_CHOICES`` has no "ready", and
Django does not enforce ``choices`` at the DB layer, so a mislabeled "ready" would
quietly persist).  ``_snapshot_image_ids`` / ``_snapshot_news_items`` filter
status="done"; a "ready" filter would silently drop every chart image.

The existing integration tests cover the positive (done) path.  These pin the
*discriminating* boundary: a section carrying any non-"done" status — especially the
Snapshot's terminal "ready" — must be EXCLUDED, so the filter can't regress to a
no-op that happens to pass the positive test.
"""

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage, SnapshotSection
from apps.threads._request import _snapshot_image_ids, _snapshot_news_items


@pytest.fixture
def snapshot(db):
    prof = TradingProfile.objects.create(name="p", style="s")
    return Snapshot.objects.create(profile=prof, status="ready")


@pytest.mark.django_db
def test_image_ids_returned_for_done_section(snapshot):
    img = SnapshotImage.objects.create(
        snapshot=snapshot, kind="server_render", data=b"png", mime_type="image/png"
    )
    SnapshotSection.objects.create(
        snapshot=snapshot, kind="image", status="done", payload={"image_ids": [img.id]}
    )
    assert _snapshot_image_ids(snapshot.id) == [img.id]


@pytest.mark.django_db
@pytest.mark.parametrize("bad_status", ["ready", "pending", "failed"])
def test_image_ids_excluded_for_non_done_section(snapshot, bad_status):
    """``ready`` is the dangerous one — it's the Snapshot's terminal value and an
    easy copy/paste mistake — but any non-done status must be excluded."""
    SnapshotSection.objects.create(
        snapshot=snapshot, kind="image", status=bad_status, payload={"image_ids": [101]}
    )
    assert _snapshot_image_ids(snapshot.id) == []


@pytest.mark.django_db
def test_news_items_excluded_for_section_mislabeled_ready(snapshot):
    SnapshotSection.objects.create(
        snapshot=snapshot, kind="news", status="ready", payload={"items": [{"id": 1}]}
    )
    assert _snapshot_news_items(snapshot.id) == []
