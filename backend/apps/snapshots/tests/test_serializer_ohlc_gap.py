"""Tests for the OHLC history-gap detector in the AI payload serializer."""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _ohlc_gap_note, _render_ohlc, serialize_for_ai


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


def test_gap_note_empty_bars():
    """Empty or single-bar list → no note."""
    assert _ohlc_gap_note([]) == ""
    assert _ohlc_gap_note(_daily_bars(["2026-05-01"])) == ""


def test_gap_note_contiguous_daily_bars_no_note():
    """Five consecutive trading days → no gap note (contiguous data)."""
    bars = _daily_bars(["2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"])
    note = _ohlc_gap_note(bars)
    assert note == "", f"Expected no note for contiguous data, got: {note!r}"


def test_gap_note_weekend_stride_no_note():
    """Mon-Fri window (5 consecutive weekdays) is contiguous — no note."""
    # A normal Mon-Fri window has all 1-day deltas; no gap above 4x threshold.
    bars = _daily_bars(["2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22"])
    note = _ohlc_gap_note(bars)
    assert note == "", f"Expected no note for Mon-Fri window, got: {note!r}"


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


def test_gap_note_clear_multi_session_hole():
    """A 4-session hole (Mon → next Monday) in otherwise daily bars → note present."""
    # Mon, Tue, Wed, then skip Thu+Fri+next Mon+next Tue = jump to next Wed (7 calendar days)
    # With daily bars Mon=7-calendar-day jump vs normal ~1-2 days → clear gap.
    bars = _daily_bars(
        [
            "2026-05-11",
            "2026-05-12",
            "2026-05-13",
            # Gap: 2026-05-14 through 2026-05-19 missing (~7 calendar days jump)
            "2026-05-20",
            "2026-05-21",
            "2026-05-22",
        ]
    )
    note = _ohlc_gap_note(bars)
    assert note != "", "Expected a gap note for a clear multi-session hole"
    assert "history gap" in note
    assert "2026-05-13" in note or "2026-05-20" in note


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


def test_gap_note_absent_for_two_bars_same_delta():
    """Two bars (only 1 delta) → median == max → no gap."""
    bars = _daily_bars(["2026-05-01", "2026-05-02"])
    note = _ohlc_gap_note(bars)
    assert note == ""


def _ohlc_payload(dates: list[str], ticker: str = "SPY", timeframe: str = "1d") -> dict:
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "bars": _daily_bars(dates),
    }


def test_render_ohlc_no_gap_note_for_contiguous():
    """_render_ohlc omits the gap note when bars are contiguous."""
    payload = _ohlc_payload(["2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"])
    out = _render_ohlc(payload)
    assert "history gap" not in out
    assert "ts,open,high,low,close,volume" in out


def test_render_ohlc_gap_note_present_for_gappy():
    """_render_ohlc appends the gap note when there is a clear hole."""
    payload = _ohlc_payload(
        [
            "2026-05-11",
            "2026-05-12",
            "2026-05-13",
            "2026-05-20",
            "2026-05-21",
            "2026-05-22",
        ]
    )
    out = _render_ohlc(payload)
    assert "history gap" in out
    assert "ts,open,high,low,close,volume" in out


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


@pytest.mark.django_db
def test_serialize_for_ai_ohlc_no_gap_note_for_contiguous_e2e():
    """Full serialize_for_ai path omits gap note for contiguous OHLC section."""
    profile = TradingProfile.objects.create(name="ohlc-nogap-test", style="s")
    snap = Snapshot.objects.create(profile=profile, includes=["ohlc"], status="ready")
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="ohlc",
        status="done",
        payload=_ohlc_payload(
            ["2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"]
        ),
    )
    out = serialize_for_ai(snap)
    assert "history gap" not in out
    assert "ts,open,high,low,close,volume" in out
