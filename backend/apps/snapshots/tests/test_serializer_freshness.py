"""Tests for the capture-freshness line in the AI payload meta block."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.serializer import serialize_for_ai


def _profile():
    return TradingProfile.objects.create(name="freshness-test", style="s")


@pytest.mark.django_db
def test_capture_freshness_line_uses_captured_at():
    """serialize_for_ai output includes 'Captured:' with the UTC timestamp and 'ago'."""
    profile = _profile()
    # captured_at is auto_now_add=True; after create(), it is set to now.
    # We freeze a time ~8 minutes in the past by updating the field directly.
    cap_time = datetime(2026, 5, 30, 14, 32, 0, tzinfo=UTC)
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    # Override captured_at to a known past time without hitting auto_now_add
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)

    assert "Captured:" in out
    # The formatted UTC timestamp should appear
    assert "2026-05-30 14:32 UTC" in out
    # Age relative to now — we can't predict exact minutes, but "ago" must be there
    assert "ago" in out


@pytest.mark.django_db
def test_capture_freshness_line_none_captured_at_no_crash():
    """If captured_at is None on an unsaved-like model object, no exception and no Captured line."""
    profile = _profile()
    # Build an unsaved Snapshot with captured_at explicitly None to test the defensive guard.
    # We must set includes to [] to avoid AttributeError on sections.all() — but since we never
    # call snapshot.sections.all() when the snap has no pk, we mock the sections relation.
    # sections.all() would fail on an unsaved instance; use a saved snap with no sections,
    # then patch captured_at to None in-memory to exercise the defensive guard.
    saved = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    saved.captured_at = None  # in-memory override only — not persisted

    # Must not raise; line should be absent
    out = serialize_for_ai(saved)
    assert "Captured:" not in out


@pytest.mark.django_db
def test_capture_freshness_line_minutes_ago():
    """Age is reported in 'minutes ago' when gap is < 1 hour."""
    profile = _profile()
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    cap_time = datetime.now(UTC) - timedelta(minutes=45)
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)
    assert "minutes ago" in out


@pytest.mark.django_db
def test_capture_freshness_line_hours_ago():
    """Age is reported in 'hours ago' when gap is >= 1 hour and < 1 day."""
    profile = _profile()
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    cap_time = datetime.now(UTC) - timedelta(hours=3)
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)
    assert "hours ago" in out


@pytest.mark.django_db
def test_capture_freshness_line_days_ago():
    """Age is reported in 'days ago' when gap is >= 1 day."""
    profile = _profile()
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    cap_time = datetime.now(UTC) - timedelta(days=2)
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)
    assert "days ago" in out


@pytest.mark.django_db
def test_capture_freshness_does_not_remove_market_closed_banner():
    """Adding the freshness line must not suppress the existing market-closed banner."""
    profile = _profile()
    snap = Snapshot.objects.create(
        profile=profile,
        includes=[],
        status="ready",
        market_state={"any_open": False, "markets": {"us_equity": {"is_open": False}}},
    )

    out = serialize_for_ai(snap)
    assert "Captured:" in out
    assert "Market state" in out
