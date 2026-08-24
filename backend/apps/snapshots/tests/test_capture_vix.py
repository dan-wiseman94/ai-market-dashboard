"""The vix section is captured on every snapshot, whatever the includes say."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture

PAYLOAD = {
    "spot": {"symbol": "$VIX", "last": 15.2, "pct_change": -3.1},
    "front": {
        "symbol": "/VXU26",
        "expiry": "2026-09-16",
        "continuous": False,
        "last": 16.8,
        "pct_change": -2.0,
        "basis": 1.6,
        "basis_pct": 10.53,
    },
    "second": {"symbol": "/VXV26", "expiry": "2026-10-21", "last": 17.9, "pct_change": -1.1},
    "contango_pct": 6.55,
    "structure": "contango",
}


def _profile():
    return TradingProfile.objects.create(name="P", style="swing")


@pytest.mark.django_db
def test_vix_appended_to_includes_and_captured():
    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 550.0}}),
        patch("apps.snapshots.services.vix_term_structure", return_value=PAYLOAD),
    ):
        snap = capture(
            profile=_profile(),
            objective="vol check",
            includes=["quotes"],
            watchlist_tickers=["SPY"],
        )
    snap.refresh_from_db()
    assert snap.includes == ["quotes", "vix"]
    vix = snap.sections.get(kind="vix")
    assert vix.status == "done"
    assert vix.payload == PAYLOAD


@pytest.mark.django_db
def test_vix_not_duplicated_when_already_included():
    with patch("apps.snapshots.services.vix_term_structure", return_value=PAYLOAD):
        snap = capture(profile=_profile(), objective="", includes=["vix"])
    snap.refresh_from_db()
    assert snap.includes == ["vix"]
    assert snap.sections.filter(kind="vix").count() == 1


@pytest.mark.django_db
def test_vix_success_cannot_rescue_all_failed_capture():
    # Auto-appended context must not flip status: when every user-requested
    # section fails, the snapshot is failed even though vix succeeded.
    with (
        patch("apps.snapshots.services.fetch_quotes", side_effect=RuntimeError("schwab down")),
        patch("apps.snapshots.services.vix_term_structure", return_value=PAYLOAD),
    ):
        snap = capture(
            profile=_profile(),
            objective="",
            includes=["quotes"],
            watchlist_tickers=["SPY"],
        )
    snap.refresh_from_db()
    assert snap.status == "failed"
    assert snap.sections.get(kind="vix").status == "done"


@pytest.mark.django_db
def test_explicitly_requested_vix_still_counts_toward_ready():
    with patch("apps.snapshots.services.vix_term_structure", return_value=PAYLOAD):
        snap = capture(profile=_profile(), objective="", includes=["vix"])
    snap.refresh_from_db()
    assert snap.status == "ready"


@pytest.mark.django_db
def test_vix_failure_fails_section_not_snapshot():
    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 550.0}}),
        patch(
            "apps.snapshots.services.vix_term_structure",
            side_effect=RuntimeError("no VIX spot or futures quotes returned"),
        ),
    ):
        snap = capture(
            profile=_profile(),
            objective="",
            includes=["quotes"],
            watchlist_tickers=["SPY"],
        )
    snap.refresh_from_db()
    assert snap.status == "ready"
    vix = snap.sections.get(kind="vix")
    assert vix.status == "failed"
    assert "no VIX spot or futures quotes returned" in vix.error
