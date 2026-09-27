"""Tests for the OHLC history-gap detector in the AI payload serializer."""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _ohlc_gap_note, serialize_for_ai


def _daily_bars(dates: list[str]) -> list[dict]:
    """Build minimal bar dicts from a list of date strings (YYYY-MM-DD)."""
    return [
        {
            "ts": f"{d}T00:00:00+00:00",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 1000,
        }
        for d in dates
    ]


def test_gap_note_week_to_week_no_note():
    """Two consecutive weeks of Mon-Fri bars — Fri-to-Mon gap is normal, no note."""
    bars = _daily_bars(
        [
            "2026-05-11",
            "2026-05-12",
            "2026-05-13",
            "2026-05-14",
            "2026-05-15",
            "2026-05-18",
            "2026-05-19",
            "2026-05-20",
            "2026-05-21",
            "2026-05-22",
        ]
    )
    note = _ohlc_gap_note(bars)
    assert note == "", f"Expected no note for two-week contiguous window, got: {note!r}"


def test_gap_note_clear_gap_names_boundary_dates():
    """The gap note includes the date before and after the gap."""
    bars = _daily_bars(
        [
            "2026-05-01",
            "2026-05-02",
            # 8-calendar-day jump — five missing sessions
            "2026-05-10",
            "2026-05-11",
            "2026-05-12",
        ]
    )
    note = _ohlc_gap_note(bars)
    assert "history gap" in note
    assert "2026-05-02" in note
    assert "2026-05-10" in note


def _ohlc_payload(dates: list[str], ticker: str = "SPY", timeframe: str = "1d") -> dict:
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "bars": _daily_bars(dates),
    }


@pytest.mark.django_db
def test_serialize_for_ai_ohlc_gap_note_e2e():
    """Full serialize_for_ai path emits gap note for a gappy OHLC section."""
    profile = TradingProfile.objects.create(name="ohlc-gap-test", style="s")
    snap = Snapshot.objects.create(profile=profile, includes=["ohlc"], status="ready")
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="ohlc",
        status="done",
        payload=_ohlc_payload(
            [
                "2026-05-05",
                "2026-05-06",
                "2026-05-14",
                "2026-05-15",
                "2026-05-16",
            ]
        ),
    )
    out = serialize_for_ai(snap)
    assert "history gap" in out
    assert "ts,open,high,low,close,volume" in out
