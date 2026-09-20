import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _render_filings, _render_treasury, serialize_for_ai


def test_render_filings_new_shape_renders_table_and_insider_line():
    payload = {
        "AAPL": {
            "filings": [
                {
                    "form": "10-K",
                    "filed": "2026-08-01",
                    "title": "Apple Inc. 10-K",
                    "url": "https://www.sec.gov/a",
                },
            ],
            "insider": [
                {
                    "form": "4",
                    "filed": "2026-09-10",
                    "title": "Apple Inc. 4",
                    "url": "https://www.sec.gov/b",
                },
            ],
        }
    }

    md = _render_filings(payload)

    assert "## SEC filings" in md
    assert "### AAPL" in md
    assert "| Form | Filed | Title |" in md
    assert "10-K" in md
    assert "2026-08-01" in md
    assert "**Insider activity (Form 4):**" in md
    assert "2026-09-10" in md
    assert "```json" not in md


def test_render_filings_legacy_flat_list_shape_still_renders_table():
    """Old persisted snapshots stored a flat list per ticker (pre-Form-4 shape)
    and must keep rendering as a table on re-render."""
    payload = {
        "AAPL": [
            {
                "form": "10-K",
                "filed": "2026-08-01",
                "title": "Apple Inc. 10-K",
                "url": "https://www.sec.gov/a",
            },
        ]
    }

    md = _render_filings(payload)

    assert "### AAPL" in md
    assert "| Form | Filed | Title |" in md
    assert "10-K" in md
    assert "**Insider activity" not in md
    assert "```json" not in md


def test_render_filings_ticker_with_only_insider_rows():
    payload = {
        "AAPL": {
            "filings": [],
            "insider": [{"form": "4", "filed": "2026-09-10", "title": "t", "url": "u"}],
        }
    }

    md = _render_filings(payload)

    assert "### AAPL" in md
    assert "**Insider activity (Form 4):**" in md
    assert "| Form | Filed | Title |" not in md


def test_render_filings_empty_payload():
    assert "_(none)_" in _render_filings({})
    assert "_(none)_" in _render_filings(None)
    assert "_(none)_" in _render_filings({"AAPL": {"filings": [], "insider": []}})
    assert "_(none)_" in _render_filings({"AAPL": []})


def test_render_treasury_renders_table_and_debt_line():
    payload = {
        "rates": {
            "record_date": "2026-08-31",
            "rates": {"Treasury Bills": 4.32, "Treasury Notes": 4.15},
        },
        "debt": {"record_date": "2026-09-01", "total_public_debt": 36_200_000_000_000.0},
    }

    md = _render_treasury(payload)

    assert "## Treasury" in md
    assert "| Security | Avg rate |" in md
    assert "Treasury Bills" in md
    assert "4.32" in md
    assert "- Debt to the penny: $36,200,000,000,000" in md
    assert "```json" not in md


def test_render_treasury_partial_failure_renders_available_half():
    # rates fetch failed (fetch_treasury degrades that sub-fetch to {}), debt succeeded.
    payload = {"rates": {}, "debt": {"record_date": "2026-09-01", "total_public_debt": 100.0}}
    md = _render_treasury(payload)
    assert "| Security | Avg rate |" not in md
    assert "Debt to the penny" in md

    # debt fetch failed, rates succeeded.
    payload2 = {"rates": {"record_date": "d", "rates": {"Treasury Bills": 4.0}}, "debt": {}}
    md2 = _render_treasury(payload2)
    assert "Treasury Bills" in md2
    assert "Debt to the penny" not in md2


def test_render_treasury_unavailable_when_empty():
    assert "_(unavailable)_" in _render_treasury({})
    assert "_(unavailable)_" in _render_treasury({"rates": {}, "debt": {}})
    assert "_(unavailable)_" in _render_treasury(None)


@pytest.mark.django_db
def test_serialize_for_ai_renders_filings_and_treasury_without_raw_json():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["filings", "treasury"], source="manual")
    SnapshotSection.objects.create(
        snapshot=s,
        kind="filings",
        status="done",
        payload={
            "AAPL": {
                "filings": [
                    {"form": "10-K", "filed": "2026-08-01", "title": "Apple 10-K", "url": "u"}
                ],
                "insider": [{"form": "4", "filed": "2026-09-10", "title": "Apple 4", "url": "u2"}],
            }
        },
    )
    SnapshotSection.objects.create(
        snapshot=s,
        kind="treasury",
        status="done",
        payload={
            "rates": {"record_date": "d", "rates": {"Treasury Bills": 4.32}},
            "debt": {"record_date": "d", "total_public_debt": 1.0},
        },
    )

    out = serialize_for_ai(s)

    assert "## SEC filings" in out
    assert "## Treasury" in out
    assert "```json" not in out
