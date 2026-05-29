"""Overnight-mode capture journey.

Covers the opt-in `overnight` snapshot path end-to-end:
- the composer renders the "Overnight (pre-market)" toggle and it is checkable;
- a capture posted with `overnight=true` runs the real pipeline (view → worker)
  and builds the futures/overseas board section, tags OHLC as an overnight
  window, and attaches gap context to quotes.

Deterministic under MOCK_EXTERNAL: the mocked Schwab client quotes every symbol
(including the board's `/ES …` futures and the overseas indices), so the board
populates without a live data provider.
"""

from __future__ import annotations

import time

import pytest
from playwright.sync_api import expect

from e2e.pages.snapshot import SnapshotPage


@pytest.mark.integration
@pytest.mark.ui
def test_overnight_toggle_renders_and_checks(page, frontend_base_url, minimal) -> None:
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    overnight = page.get_by_role("checkbox", name="Overnight (pre-market)")
    expect(overnight).to_be_visible(timeout=10_000)
    expect(overnight).not_to_be_checked()
    overnight.check()
    expect(overnight).to_be_checked()
    # The explanatory hint appears only once the toggle is on.
    expect(page.get_by_text("shift to extended hours", exact=False)).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_overnight_capture_pipeline_builds_board(api_client, minimal) -> None:
    """POST overnight=true and verify the real capture pipeline enriches sections.

    Mirrors the api_client+poll pattern of the partial-failure test: capture runs
    in the worker, so poll the detail endpoint until it settles, then assert the
    overnight-specific outcomes that only the new code path produces.
    """
    from apps.profiles.models import TradingProfile

    profile = TradingProfile.objects.first()
    assert profile is not None

    r = api_client.post(
        "/api/snapshots/",
        json={
            "profile_id": profile.id,
            "objective": "overnight pre-market read",
            "includes": ["quotes", "ohlc"],
            "watchlist_tickers": ["SPY"],
            "ohlc_ticker": "SPY",
            "ohlc_timeframe": "1m",
            "overnight": True,
        },
    )
    assert r.status_code == 202, r.text
    snap_id = r.json()["id"]

    body: dict = {}
    for _ in range(30):
        body = api_client.get(f"/api/snapshots/{snap_id}/").json()
        if body["status"] != "pending":
            break
        time.sleep(1)

    assert body.get("status") == "ready", body
    # The opt-in flag persisted and the board section was auto-added to includes.
    assert body["overnight"] is True, body
    assert "overnight" in body["includes"], body["includes"]

    sections = {s["kind"]: s for s in body["sections"]}

    # 1) The futures/overseas board was captured and populated (mock quotes /ES…).
    assert sections["overnight"]["status"] == "done", sections["overnight"]
    board = sections["overnight"]["payload"]
    assert board["futures"], f"expected futures in board, got {board}"
    assert "/ES" in board["futures"], board["futures"]

    # 2) OHLC was fetched on the overnight (extended-hours) window, coarsened to 5m.
    ohlc = sections["ohlc"]["payload"]
    assert ohlc["window"] == "overnight", ohlc
    assert ohlc["timeframe"] == "5m", ohlc  # 1m request coarsened on the overnight path

    # 3) Quotes carry gap context (mock returns closePrice → gap_pct computed).
    quotes = sections["quotes"]["payload"]
    assert "gap_pct" in quotes.get("SPY", {}), quotes
