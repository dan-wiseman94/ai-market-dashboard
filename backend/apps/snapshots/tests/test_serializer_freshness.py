"""Tests for the capture-freshness line in the AI payload meta block."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.snapshots.models import Snapshot
from apps.snapshots.serializer import serialize_for_ai


@pytest.mark.django_db
def test_capture_freshness_line_uses_captured_at(profile):
    """serialize_for_ai output includes 'Captured:' with the UTC timestamp and 'ago'."""
    # captured_at is auto_now_add=True; after create(), it is set to now.
    # We freeze a time ~8 minutes in the past by updating the field directly.
    cap_time = datetime(2026, 5, 30, 14, 32, 0, tzinfo=UTC)
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    # Override captured_at to a known past time without hitting auto_now_add
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)

    assert "Captured:" in out
    assert "2026-05-30 14:32 UTC" in out
    # Age relative to now — we can't predict exact minutes, but "ago" must be there
    assert "ago" in out


@pytest.mark.django_db
def test_capture_freshness_line_minutes_ago(profile):
    """Age is reported in 'minutes ago' when gap is < 1 hour."""
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    cap_time = datetime.now(UTC) - timedelta(minutes=45)
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)
    assert "minutes ago" in out


@pytest.mark.django_db
def test_capture_freshness_line_hours_ago(profile):
    """Age is reported in 'hours ago' when gap is >= 1 hour and < 1 day."""
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    cap_time = datetime.now(UTC) - timedelta(hours=3)
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)
    assert "hours ago" in out


@pytest.mark.django_db
def test_capture_freshness_line_days_ago(profile):
    """Age is reported in 'days ago' when gap is >= 1 day."""
    snap = Snapshot.objects.create(profile=profile, includes=[], status="ready")
    cap_time = datetime.now(UTC) - timedelta(days=2)
    Snapshot.objects.filter(pk=snap.pk).update(captured_at=cap_time)
    snap.refresh_from_db()

    out = serialize_for_ai(snap)
    assert "days ago" in out
