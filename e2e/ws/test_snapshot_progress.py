"""snapshot.<id> — per-section progress events + terminal status last.

Fixes the prior skip: the create endpoint wants ``profile_id`` (not a ``profile``
name → 400), and the capture broadcasts flat ``section_started`` / ``section_done``
/ ``section_failed`` frames keyed ``kind`` at the top level — there is no
``section_status`` event and no ``data`` wrapper (apps/snapshots/services).
"""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


def _profile_id(api_base_url: str, name: str) -> int | None:
    r = httpx.get(f"{api_base_url}/api/profiles/", timeout=5)
    r.raise_for_status()
    rows = r.json()
    rows = rows.get("results", rows) if isinstance(rows, dict) else rows
    for row in rows:
        if row.get("name") == name:
            return int(row["id"])
    return None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_snapshot_progress_per_section(ws_base_url, api_base_url, minimal) -> None:
    pid = _profile_id(api_base_url, "E2E Default")
    if pid is None:
        pytest.skip("seeded profile 'E2E Default' not found")

    r = httpx.post(
        f"{api_base_url}/api/snapshots/",
        json={"profile_id": pid, "objective": "ws progress test"},
        timeout=5,
    )
    assert r.status_code in (200, 201, 202), f"snapshot create failed: {r.status_code} {r.text}"
    sid = r.json()["id"]

    wc = await WsClient.connect(f"{ws_base_url}/ws/snapshots/{sid}/")
    try:
        # Capture is a synchronous loop over includes; it ends with a terminal
        # status frame ("ready"/"failed"). Wait for that, then inspect the
        # per-section frames that preceded it.
        await wc.wait_for_event("ready", timeout=30.0)
        started = wc.events_of("section_started")
        assert started, f"expected section_started frames; got {[e for e in wc._events]}"
        assert all(e.get("kind") for e in started), started
    finally:
        await wc.close()
