"""Fed communication section rendering for the AI payload.

`_render_fed` always looks up the next FOMC decision from `apps.market.models.
MarketEvent` (kind="fomc"), so every test here needs DB access — matches the
market app's own MarketEvent test fixtures (test_events_model.py).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _render_fed, _title, serialize_for_ai


@pytest.mark.django_db
def test_render_fed_lists_items_newest_field_order():
    payload = {
        "items": [
            {
                "kind": "press_monetary",
                "title": "FOMC statement",
                "url": "https://www.federalreserve.gov/a.htm",
                "published": "2026-09-16T18:00:00+00:00",
                "summary": "...",
            },
            {
                "kind": "speeches",
                "title": "Chair speech",
                "url": "https://www.federalreserve.gov/b.htm",
                "published": "2026-09-15T14:00:00+00:00",
                "summary": "...",
            },
        ]
    }
    out = _render_fed(payload)
    assert out.startswith("## Fed communication")
    assert (
        "- **2026-09-16** [press_monetary] [FOMC statement](https://www.federalreserve.gov/a.htm)"
        in out
    )
    assert "- **2026-09-15** [speeches] [Chair speech](https://www.federalreserve.gov/b.htm)" in out


@pytest.mark.django_db
def test_render_fed_caps_at_ten_items():
    items = [
        {
            "kind": "speeches",
            "title": f"Speech {i}",
            "url": f"https://example.com/{i}",
            "published": "2026-09-01T00:00:00+00:00",
            "summary": "",
        }
        for i in range(15)
    ]
    out = _render_fed({"items": items})
    assert sum(1 for line in out.split("\n") if line.startswith("- **")) == 10


@pytest.mark.django_db
def test_render_fed_empty_items_honest_fallback():
    out = _render_fed({"items": []})
    assert "## Fed communication" in out
    assert "_(no recent Fed communications)_" in out


@pytest.mark.django_db
def test_render_fed_non_dict_payload_treated_as_no_items():
    out = _render_fed("garbage")
    assert "_(no recent Fed communications)_" in out


@pytest.mark.django_db
def test_render_fed_includes_next_fomc_line_when_future_event_exists():
    ev = MarketEvent.objects.create(
        source="seed",
        external_id="FOMC:test",
        kind="fomc",
        title="FOMC decision",
        event_time=timezone.now() + timedelta(days=9),
    )
    out = _render_fed({"items": []})
    lines = out.split("\n")
    assert lines[0] == "## Fed communication"
    assert lines[1].startswith("- Next FOMC decision in ")
    assert ev.event_time.date().isoformat() in lines[1]


@pytest.mark.django_db
def test_render_fed_omits_next_fomc_line_when_no_future_event():
    out = _render_fed({"items": []})
    assert "Next FOMC" not in out


@pytest.mark.django_db
def test_render_fed_ignores_past_fomc_events():
    MarketEvent.objects.create(
        source="seed",
        external_id="FOMC:past",
        kind="fomc",
        title="FOMC decision",
        event_time=timezone.now() - timedelta(days=3),
    )
    out = _render_fed({"items": []})
    assert "Next FOMC" not in out


def test_fed_title():
    assert _title("fed") == "Fed communication"


@pytest.mark.django_db
def test_done_fed_section_renders_markdown_in_full_flow():
    # Pins the _RENDERERS["fed"] registration: without it, _render_section
    # falls back to a raw ```json dict dump on every snapshot.
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["fed"], source="manual", status="ready")
    SnapshotSection.objects.create(
        snapshot=s,
        kind="fed",
        status="done",
        payload={
            "items": [
                {
                    "kind": "speeches",
                    "title": "Chair speech",
                    "url": "https://www.federalreserve.gov/a.htm",
                    "published": "2026-09-15T14:00:00+00:00",
                    "summary": "",
                }
            ]
        },
    )
    out = serialize_for_ai(s)
    assert "## Fed communication" in out
    assert "Chair speech" in out
    assert "```json" not in out


@pytest.mark.django_db
def test_failed_fed_section_renders_unavailable_with_proper_title():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["fed"], source="manual", status="ready")
    SnapshotSection.objects.create(
        snapshot=s, kind="fed", status="failed", payload={}, error="ValueError: x"
    )
    out = serialize_for_ai(s)
    assert "## Fed communication" in out
    assert "unavailable" in out
