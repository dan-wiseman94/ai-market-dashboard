"""Tests for the thesis app — model, CRUD API, close action, run-postmortem stub,
and the create-from-source entry_price defaulting behaviour."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.thesis.models import Thesis
from apps.threads.models import Thread


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="Test Profile", style="swing trader")


@pytest.fixture
def thread(db, profile):
    return Thread.objects.create(kind="consult", title="AAPL thesis thread", profile=profile)


@pytest.fixture
def snapshot(db, profile):
    return Snapshot.objects.create(
        profile=profile, includes=["quotes"], source="manual", status="ready"
    )


@pytest.fixture
def snapshot_with_quotes(db, snapshot):
    """Snapshot with a done quotes section containing AAPL last price."""
    SnapshotSection.objects.create(
        snapshot=snapshot,
        kind="quotes",
        status="done",
        payload={"AAPL": {"last": 187.5, "bid": 187.0, "ask": 188.0}},
    )
    return snapshot


@pytest.mark.django_db
def test_ticker_uppercased_on_save(profile):
    t = Thesis.objects.create(
        title="Long AAPL",
        ticker="aapl",
        direction="bullish",
        profile=profile,
    )
    assert t.ticker == "AAPL"


@pytest.mark.django_db
def test_ticker_already_upper_stays(profile):
    t = Thesis.objects.create(title="Long SPY", ticker="SPY", direction="bearish", profile=profile)
    assert t.ticker == "SPY"


@pytest.mark.django_db
def test_ticker_stripped_on_save(profile):
    t = Thesis.objects.create(
        title="Long NVDA",
        ticker=" nvda ",
        direction="bullish",
        profile=profile,
    )
    assert t.ticker == "NVDA"


@pytest.mark.django_db
def test_defaults(profile):
    t = Thesis.objects.create(title="test", ticker="TSLA", direction="neutral", profile=profile)
    assert t.conviction == 3
    assert t.horizon_days == 30
    assert t.status == "open"
    assert t.rationale == ""
    assert t.entry_price is None
    assert t.close_note == ""
    assert t.closed_at is None


@pytest.mark.django_db
def test_str(profile):
    t = Thesis.objects.create(title="x", ticker="nvda", direction="bullish", profile=profile)
    assert "NVDA" in str(t)
    assert "bullish" in str(t)
    assert "open" in str(t)


@pytest.mark.django_db
def test_create_minimal(api, profile):
    resp = api.post(
        "/api/theses/",
        {
            "title": "Long NVDA",
            "ticker": "nvda",
            "direction": "bullish",
            "profile_id": profile.id,
            "rationale": "AI compute demand",
            "invalidation_note": "breaks below 100",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["ticker"] == "NVDA"
    assert body["status"] == "open"
    assert body["conviction"] == 3
    assert body["profile_id"] == profile.id


@pytest.mark.django_db
def test_create_requires_rationale_and_invalidation(api, profile):
    """Pre-trade discipline: a new thesis must state a rationale AND an
    invalidation (a price level OR a written note), or the create is rejected."""
    base = {
        "title": "undisciplined",
        "ticker": "NVDA",
        "direction": "bullish",
        "profile_id": profile.id,
    }

    r1 = api.post("/api/theses/", base, format="json")
    assert r1.status_code == 400
    assert "rationale" in r1.json()

    r2 = api.post("/api/theses/", {**base, "rationale": "AI demand"}, format="json")
    assert r2.status_code == 400
    assert "invalidation_note" in r2.json()

    r3 = api.post(
        "/api/theses/",
        {**base, "rationale": "AI demand", "invalidation_price": "95.00"},
        format="json",
    )
    assert r3.status_code == 201

    r4 = api.post(
        "/api/theses/",
        {**base, "rationale": "AI demand", "invalidation_note": "breaks below 100"},
        format="json",
    )
    assert r4.status_code == 201
    assert r4.json()["invalidation_note"] == "breaks below 100"


@pytest.mark.django_db
def test_list(api, profile):
    Thesis.objects.create(title="a", ticker="A", direction="bullish", profile=profile)
    Thesis.objects.create(title="b", ticker="B", direction="bearish", profile=profile)
    resp = api.get("/api/theses/", format="json")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.django_db
def test_retrieve(api, profile):
    t = Thesis.objects.create(
        title="retrieve me", ticker="AMD", direction="neutral", profile=profile
    )
    resp = api.get(f"/api/theses/{t.id}/", format="json")
    assert resp.status_code == 200
    assert resp.json()["id"] == t.id


@pytest.mark.django_db
def test_patch(api, profile):
    t = Thesis.objects.create(title="patch me", ticker="META", direction="bullish", profile=profile)
    resp = api.patch(f"/api/theses/{t.id}/", {"conviction": 5}, format="json")
    assert resp.status_code == 200
    assert resp.json()["conviction"] == 5


@pytest.mark.django_db
def test_delete(api, profile):
    t = Thesis.objects.create(
        title="delete me", ticker="GOOG", direction="bearish", profile=profile
    )
    resp = api.delete(f"/api/theses/{t.id}/")
    assert resp.status_code == 204
    assert not Thesis.objects.filter(id=t.id).exists()


@pytest.mark.django_db
def test_close_win(api, profile):
    t = Thesis.objects.create(title="winner", ticker="AAPL", direction="bullish", profile=profile)
    resp = api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "closed_win", "close_note": "hit target"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "closed_win"
    assert body["close_note"] == "hit target"
    assert body["closed_at"] is not None
    t.refresh_from_db()
    assert t.status == "closed_win"
    assert t.closed_at is not None


@pytest.mark.django_db
def test_close_loss(api, profile):
    t = Thesis.objects.create(title="loser", ticker="TSLA", direction="bearish", profile=profile)
    resp = api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "closed_loss", "close_note": "stopped out"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed_loss"


@pytest.mark.django_db
def test_close_invalidated(api, profile):
    t = Thesis.objects.create(
        title="invalidated", ticker="AMD", direction="bullish", profile=profile
    )
    resp = api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "invalidated"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalidated"


@pytest.mark.django_db
def test_close_rejects_open_status(api, profile):
    t = Thesis.objects.create(
        title="still open", ticker="SPY", direction="neutral", profile=profile
    )
    resp = api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "open"},
        format="json",
    )
    assert resp.status_code == 400
    t.refresh_from_db()
    assert t.status == "open"


@pytest.mark.django_db
def test_close_rejects_missing_status(api, profile):
    t = Thesis.objects.create(title="no status", ticker="QQQ", direction="bullish", profile=profile)
    resp = api.post(f"/api/theses/{t.id}/close/", {}, format="json")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# run-postmortem endpoint (full behaviour covered in test_postmortem.py)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_postmortem_returns_202(api, profile):
    t = Thesis.objects.create(title="pm", ticker="NVDA", direction="bullish", profile=profile)
    with patch("apps.thesis.views.run_postmortem_task.delay") as mock_delay:
        resp = api.post(f"/api/theses/{t.id}/run-postmortem/", format="json")
    assert resp.status_code == 202
    assert "postmortem_id" in resp.json()
    mock_delay.assert_called_once()


@pytest.mark.django_db
def test_create_with_snapshot_defaults_entry_price(api, profile, snapshot_with_quotes):
    resp = api.post(
        "/api/theses/",
        {
            "title": "AAPL long",
            "rationale": "AAPL uptrend intact",
            "invalidation_note": "loses 180 support",
            "ticker": "AAPL",
            "direction": "bullish",
            "profile_id": profile.id,
            "snapshot_id": snapshot_with_quotes.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["entry_price"] is not None
    assert float(body["entry_price"]) == pytest.approx(187.5)
    assert body["snapshot_id"] == snapshot_with_quotes.id


@pytest.mark.django_db
def test_create_with_snapshot_does_not_override_explicit_entry_price(
    api, profile, snapshot_with_quotes
):
    resp = api.post(
        "/api/theses/",
        {
            "title": "AAPL long explicit",
            "rationale": "AAPL uptrend intact",
            "invalidation_note": "loses 180 support",
            "ticker": "AAPL",
            "direction": "bullish",
            "profile_id": profile.id,
            "snapshot_id": snapshot_with_quotes.id,
            "entry_price": "200.00",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert float(resp.json()["entry_price"]) == pytest.approx(200.0)


@pytest.mark.django_db
def test_create_with_thread_sets_thread_fk(api, profile, thread):
    resp = api.post(
        "/api/theses/",
        {
            "title": "from thread",
            "rationale": "thread analysis",
            "invalidation_note": "thesis broken below support",
            "ticker": "AAPL",
            "direction": "bullish",
            "profile_id": profile.id,
            "thread_id": thread.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["thread_id"] == thread.id


@pytest.mark.django_db
def test_create_with_snapshot_no_quotes_section_leaves_entry_price_null(api, profile, snapshot):
    """Snapshot exists but has no done quotes section — entry_price stays null."""
    resp = api.post(
        "/api/theses/",
        {
            "title": "AAPL long no quotes",
            "rationale": "AAPL thesis",
            "invalidation_note": "loses 180 support",
            "ticker": "AAPL",
            "direction": "bullish",
            "profile_id": profile.id,
            "snapshot_id": snapshot.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["entry_price"] is None


@pytest.mark.django_db
def test_create_with_snapshot_ticker_not_in_quotes_leaves_entry_price_null(api, profile):
    """Quotes section exists but doesn't have the thesis ticker."""
    snap = Snapshot.objects.create(
        profile=profile, includes=["quotes"], source="manual", status="ready"
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="quotes",
        status="done",
        payload={"SPY": {"last": 500.0}},
    )
    resp = api.post(
        "/api/theses/",
        {
            "title": "AAPL long missing ticker",
            "rationale": "AAPL thesis",
            "invalidation_note": "loses 180 support",
            "ticker": "AAPL",
            "direction": "bullish",
            "profile_id": profile.id,
            "snapshot_id": snap.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["entry_price"] is None


@pytest.mark.django_db
def test_patch_status_ignored_on_closed_thesis(api, profile):
    """PATCH {status: 'open'} on a closed thesis must NOT reopen it (fix C)."""
    t = Thesis.objects.create(
        title="closed one", ticker="AMZN", direction="bullish", profile=profile
    )
    close_resp = api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "closed_win", "close_note": "nice profit"},
        format="json",
    )
    assert close_resp.status_code == 200

    patch_resp = api.patch(f"/api/theses/{t.id}/", {"status": "open"}, format="json")
    assert patch_resp.status_code == 200  # PATCH itself succeeds (field is silently ignored)
    t.refresh_from_db()
    assert t.status == "closed_win"


@pytest.mark.django_db
def test_create_conviction_too_high_returns_400(api, profile):
    """conviction=99 must be rejected with 400 (fix D — model validator via DRF)."""
    resp = api.post(
        "/api/theses/",
        {
            "title": "over-confident",
            "ticker": "NVDA",
            "direction": "bullish",
            "profile_id": profile.id,
            "rationale": "documented reasoning",
            "invalidation_note": "thesis broken below support",
            "conviction": 99,
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_create_conviction_zero_returns_400(api, profile):
    """conviction=0 must be rejected with 400 (fix D — model validator via DRF)."""
    resp = api.post(
        "/api/theses/",
        {
            "title": "zero confidence",
            "ticker": "TSLA",
            "direction": "bearish",
            "profile_id": profile.id,
            "rationale": "documented reasoning",
            "invalidation_note": "thesis broken below support",
            "conviction": 0,
        },
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_run_postmortem_404_for_unknown_pk(api):
    """run-postmortem must return 404 when the thesis does not exist (fix G)."""
    resp = api.post("/api/theses/999999/run-postmortem/", format="json")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_reclose_without_note_preserves_existing_note(api, profile):
    """A second close call without close_note must preserve the original note (fix F)."""
    t = Thesis.objects.create(
        title="two closes", ticker="SPY", direction="neutral", profile=profile
    )
    api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "closed_win", "close_note": "original note"},
        format="json",
    )
    t.refresh_from_db()
    assert t.close_note == "original note"

    api.post(
        f"/api/theses/{t.id}/close/",
        {"status": "closed_loss"},
        format="json",
    )
    t.refresh_from_db()
    assert t.close_note == "original note"


@pytest.mark.django_db
def test_create_lowercase_ticker_defaults_entry_price_from_uppercase_quotes_key(
    api, profile, snapshot_with_quotes
):
    """ticker='aapl' (lowercase) should still match the 'AAPL' key in the snapshot quotes."""
    resp = api.post(
        "/api/theses/",
        {
            "title": "AAPL long lowercase ticker",
            "rationale": "AAPL uptrend intact",
            "invalidation_note": "loses 180 support",
            "ticker": "aapl",
            "direction": "bullish",
            "profile_id": profile.id,
            "snapshot_id": snapshot_with_quotes.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["entry_price"] is not None
    assert float(body["entry_price"]) == pytest.approx(187.5)
