"""Endpoint shapes for the coverage API (M14 F3).

GET  /api/coverage/            -> list of notes (lean, no revisions inlined)
GET  /api/coverage/<ticker>/   -> the note + its full revision history
POST /api/coverage/<ticker>/revise/ -> manual revision against the latest snapshot
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.strategy.models import CoverageNote, CoverageRevision


def _items(resp):
    data = resp.json()
    return data["results"] if isinstance(data, dict) and "results" in data else data


@pytest.mark.django_db
def test_list_returns_notes_without_revisions():
    client = APIClient()
    CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)
    CoverageNote.objects.create(ticker="QQQ", stance="bear", conviction=2)

    resp = client.get("/api/coverage/")
    assert resp.status_code == 200
    items = _items(resp)
    assert {"SPY", "QQQ"} <= {it["ticker"] for it in items}
    assert "revisions" not in items[0]  # list stays lean


@pytest.mark.django_db
def test_retrieve_returns_note_with_revisions_case_insensitive():
    client = APIClient()
    note = CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)
    CoverageRevision.objects.create(
        note=note, prior={}, new={"stance": "bull"}, reason="established"
    )
    CoverageRevision.objects.create(
        note=note, prior={"stance": "bull"}, new={"stance": "bear"}, reason="lost 520"
    )

    resp = client.get("/api/coverage/spy/")  # lowercase resolves to the SPY note
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "SPY"
    assert data["stance"] == "bull"
    assert len(data["revisions"]) == 2
    assert {r["reason"] for r in data["revisions"]} == {"established", "lost 520"}


@pytest.mark.django_db
def test_retrieve_unknown_ticker_404():
    resp = APIClient().get("/api/coverage/NOPE/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_manual_revise_uses_latest_snapshot(monkeypatch):
    profile = TradingProfile.objects.create(name="p", style="s", default_provider="claude")
    note = CoverageNote.objects.create(ticker="SPY", stance="neutral", conviction=1)
    snap = Snapshot.objects.create(
        profile=profile, status="ready", primary_ticker="SPY", source="manual"
    )

    called = {}

    def fake_revise(ticker, snapshot, *, profile):
        called.update(ticker=ticker, snap_id=snapshot.id, profile_id=profile.id)
        return CoverageRevision.objects.create(note=note, prior={}, new={}, reason="manual")

    monkeypatch.setattr("apps.strategy.coverage.views.revise_coverage", fake_revise)

    resp = APIClient().post("/api/coverage/SPY/revise/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["revised"] is True
    assert data["note"]["ticker"] == "SPY"
    assert called == {"ticker": "SPY", "snap_id": snap.id, "profile_id": profile.id}


@pytest.mark.django_db
def test_manual_revise_no_snapshot_returns_400():
    CoverageNote.objects.create(ticker="SPY", stance="neutral", conviction=1)
    resp = APIClient().post("/api/coverage/SPY/revise/")
    assert resp.status_code == 400
