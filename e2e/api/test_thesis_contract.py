"""Thesis + decision-journal API contract (M11 second brain).

Previously the entire thesis/post-mortem/journal surface had no E2E coverage.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_theses_list(api_client, thesis) -> None:
    r = api_client.get("/api/theses/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)
    titles = {row["title"] for row in rows}
    assert {"E2E open thesis", "E2E closed thesis"} <= titles


@pytest.mark.integration
def test_thesis_retrieve_nests_postmortems(api_client, thesis) -> None:
    from apps.thesis.models import Thesis

    open_id = Thesis.objects.get(title="E2E open thesis").id
    r = api_client.get(f"/api/theses/{open_id}/")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["direction"] == "bullish"
    assert body["status"] == "open"
    # schedule_postmortems lays down one PM per configured horizon.
    assert isinstance(body["postmortems"], list)
    assert len(body["postmortems"]) >= 1
    assert {"horizon_days", "status", "verdict"} <= set(body["postmortems"][0])


@pytest.mark.integration
def test_thesis_create_schedules_postmortems(api_client, threads) -> None:
    payload = {
        "title": "E2E created thesis",
        "ticker": "nvda",
        "direction": "bullish",
        "conviction": 5,
        "horizon_days": 30,
        "rationale": "E2E rationale",
        "invalidation_note": "breaks below support",
    }
    r = api_client.post("/api/theses/", json=payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ticker"] == "NVDA"  # model upper-cases the ticker on save
    assert body["status"] == "open"  # status is read-only on create
    assert len(body["postmortems"]) >= 1


@pytest.mark.integration
def test_thesis_close_transitions_status(api_client, thesis) -> None:
    from apps.thesis.models import Thesis

    # Use the seeded create endpoint so we don't mutate the shared open fixture.
    created = api_client.post(
        "/api/theses/",
        json={
            "title": "E2E closable thesis",
            "ticker": "MSFT",
            "direction": "neutral",
            "rationale": "E2E rationale",
            "invalidation_note": "breaks below support",
        },
    ).json()
    r = api_client.post(
        f"/api/theses/{created['id']}/close/",
        json={"status": "closed_scratch", "close_note": "flat"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "closed_scratch"
    assert Thesis.objects.get(id=created["id"]).closed_at is not None


@pytest.mark.integration
def test_thesis_close_rejects_bad_status(api_client, thesis) -> None:
    from apps.thesis.models import Thesis

    open_id = Thesis.objects.get(title="E2E open thesis").id
    r = api_client.post(f"/api/theses/{open_id}/close/", json={"status": "open"})
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_status"


@pytest.mark.integration
def test_thesis_run_postmortem_returns_202(api_client, thesis) -> None:
    from apps.thesis.models import Thesis

    open_id = Thesis.objects.get(title="E2E open thesis").id
    r = api_client.post(f"/api/theses/{open_id}/run-postmortem/")
    assert r.status_code == 202, r.text
    body = r.json()
    assert "postmortem_id" in body


@pytest.mark.integration
def test_journal_create_and_filter_by_thread(api_client, thesis) -> None:
    from apps.threads.models import Thread

    thread_id = Thread.objects.order_by("id").first().id
    r = api_client.post(
        "/api/journal/",
        json={"thread_id": thread_id, "decision": "watching", "note": "via e2e"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["decision"] == "watching"

    listed = api_client.get(f"/api/journal/?thread={thread_id}")
    assert listed.status_code == 200
    rows = listed.json()
    rows = rows if isinstance(rows, list) else rows.get("results", rows)
    assert all(row["thread_id"] == thread_id for row in rows)
    assert any(row["decision"] == "watching" for row in rows)
