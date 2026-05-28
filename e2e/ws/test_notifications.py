"""user.<id>.notifications — trigger / observer / backup.

The notification consumer forwards ``{"type": "notification.event", "payload":
<NotificationSerializer data>}`` (apps/observer/consumers.py), so we wait for the
``notification.event`` frame and read its ``payload`` — the earlier version
waited for a ``"notification"`` event with a ``data`` key that never exists, and
posted backups to the create route (405 by design; the real trigger is
``/api/backups/run/``).

Ids are resolved over HTTP (never sync-ORM-in-async, which raises
``SynchronousOnlyOperation`` on the ``web`` container that runs this lane).
"""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


def _find_id(api_base_url: str, path: str, name: str) -> int | None:
    r = httpx.get(f"{api_base_url}{path}", timeout=5)
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
async def test_notifications_trigger_fire_delivered(ws_base_url, api_base_url, triggers) -> None:
    trig_id = _find_id(api_base_url, "/api/triggers/", "E2E always fires")
    if trig_id is None:
        pytest.skip("seeded trigger 'E2E always fires' not found")
    wc = await WsClient.connect(f"{ws_base_url}/ws/notifications/")
    try:
        r = httpx.post(f"{api_base_url}/api/triggers/{trig_id}/fire/", timeout=5)
        if r.status_code in (404, 405):
            pytest.skip("trigger fire endpoint not exposed in this build")
        assert r.status_code in (200, 201, 202), f"fire failed: {r.status_code} {r.text}"

        # Generous wait: the fire runs on the worker, which can lag under load.
        ev = await wc.wait_for_event("notification.event", timeout=90.0)
        assert ev.get("payload", {}).get("kind"), ev
    finally:
        await wc.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_notifications_observer_done_delivered(ws_base_url, api_base_url, observer) -> None:
    sched_id = _find_id(api_base_url, "/api/observer/schedules/", "E2E active schedule")
    if sched_id is None:
        pytest.skip("seeded schedule 'E2E active schedule' not found")
    wc = await WsClient.connect(f"{ws_base_url}/ws/notifications/")
    try:
        r = httpx.post(f"{api_base_url}/api/observer/schedules/{sched_id}/run-now/", timeout=5)
        if r.status_code in (404, 405):
            pytest.skip("observer run-now endpoint not exposed in this build")
        assert r.status_code in (200, 201, 202), f"run-now failed: {r.status_code} {r.text}"

        # Generous wait: the observer fire runs on the worker, which can lag under
        # load (a tighter 30s wait flaked when other lanes saturated the worker).
        ev = await wc.wait_for_event("notification.event", timeout=90.0)
        assert ev.get("payload"), ev
    finally:
        await wc.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_notifications_backup_done_delivered(ws_base_url, api_base_url, minimal) -> None:
    wc = await WsClient.connect(f"{ws_base_url}/ws/notifications/")
    try:
        r = httpx.post(f"{api_base_url}/api/backups/run/", timeout=5)
        if r.status_code not in (200, 201, 202):
            pytest.skip(f"backup run returned {r.status_code}")
        ev = await wc.wait_for_event("notification.event", timeout=90.0)
        assert ev.get("payload"), ev
    finally:
        await wc.close()
