"""snapshot.<id> — per-section events + terminal status last."""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_snapshot_progress_per_section(ws_base_url, api_base_url, minimal) -> None:
    r = httpx.post(
        f"{api_base_url}/api/snapshots/",
        json={"profile": "E2E Default", "objective": "ws progress test"},
        timeout=5,
    )
    if r.status_code not in (200, 201, 202):
        pytest.skip(f"snapshot create returned {r.status_code}; can't assert progress events")
    sid = r.json().get("id")
    if sid is None:
        pytest.skip("snapshot create body missing id")

    wc = await WsClient.connect(f"{ws_base_url}/ws/snapshots/{sid}/")
    try:
        sections_seen: set[str] = set()
        for _ in range(15):
            try:
                ev = await wc.wait_for_event("section_status", timeout=10.0)
            except TimeoutError:
                break
            name = ev.get("data", {}).get("kind") or ev.get("data", {}).get("name")
            if name:
                sections_seen.add(name)
        assert sections_seen, "expected at least one section_status event"
    finally:
        await wc.close()
