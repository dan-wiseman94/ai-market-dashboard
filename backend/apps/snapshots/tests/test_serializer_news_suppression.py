"""News reaches Claude twice in one turn — as citable `search_result` blocks and
as rendered prose in the snapshot payload. These pin the two seams the request
layer uses to send it once, and the default that keeps the payload readable.
"""

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import (
    NEWS_AS_CITATIONS_NOTE,
    NEWS_HEADING,
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


def test_prose_is_the_default():
    text = serialize_for_ai(_snapshot())
    assert "Chips rip" in text
    assert NEWS_AS_CITATIONS_NOTE not in text


def test_suppressed_prose_leaves_a_pointer_not_a_hole():
    text = serialize_for_ai(_snapshot(), include_news_prose=False)
    assert "Chips rip" not in text
    assert NEWS_AS_CITATIONS_NOTE in text
    assert "## Quotes" in text  # every other section is untouched


def test_strip_matches_the_serialize_time_suppression_byte_for_byte():
    snap = _snapshot()
    assert strip_news_section(serialize_for_ai(snap)) == serialize_for_ai(
        snap, include_news_prose=False
    )


def test_strip_keeps_a_trailing_section_intact():
    snap = _snapshot(includes=("news", "quotes"))
    stripped = strip_news_section(serialize_for_ai(snap))
    assert "Chips rip" not in stripped
    assert "## Quotes" in stripped
    assert "500" in stripped


def test_strip_is_a_no_op_without_a_news_section():
    text = serialize_for_ai(_snapshot(includes=("quotes",)))
    assert strip_news_section(text) == text


def test_strip_keeps_the_pruned_note_that_follows_the_news_section():
    # The footnote is the one part that is neither a section nor inside one, so it
    # is the boundary the cut would otherwise run straight through.
    text = "\n\n".join(
        [
            "## Quotes\n| SPY | 500 |",
            f"{NEWS_HEADING}\n\n- **1m ago** — *Reuters* — Chips rip",
            "_(pruned for token budget: chain, ohlc)_",
        ]
    )
    stripped = strip_news_section(text)
    assert "Chips rip" not in stripped
    assert stripped.endswith("_(pruned for token budget: chain, ohlc)_")
    assert NEWS_AS_CITATIONS_NOTE in stripped


def test_a_failed_news_section_still_reports_unavailable():
    # No items means no citation blocks either — suppressing the prose would hide
    # the failure rather than de-duplicate it.
    text = serialize_for_ai(_snapshot(news_status="failed"), include_news_prose=False)
    assert "unavailable" in text
    assert NEWS_AS_CITATIONS_NOTE not in text
