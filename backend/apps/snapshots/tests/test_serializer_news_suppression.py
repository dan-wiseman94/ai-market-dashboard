"""News reaches Claude twice in one turn — as citable `search_result` blocks and
as rendered prose in the snapshot payload. These pin the two seams the request
layer uses to send it once, and the default that keeps the payload readable.
"""

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import (
    serialize_for_ai,
    strip_news_section,
)

pytestmark = pytest.mark.django_db

_ITEMS = [
    {"headline": "Chips rip", "source": "Reuters", "summary": "Semis lead the tape."},
    {"headline": "Yields ease", "source": "WSJ", "summary": "Tens back under 4%."},
]


def _snapshot(*, includes=("quotes", "news"), news_status="done") -> Snapshot:
    p = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(
        profile=p, includes=list(includes), source="manual", status="ready"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"SPY": {"last": 500.0}}
    )
    if "news" in includes:
        SnapshotSection.objects.create(
            snapshot=snap, kind="news", status=news_status, payload={"items": _ITEMS}
        )
    return snap


def test_strip_matches_the_serialize_time_suppression_byte_for_byte():
    snap = _snapshot()
    assert strip_news_section(serialize_for_ai(snap)) == serialize_for_ai(
        snap, include_news_prose=False
    )
