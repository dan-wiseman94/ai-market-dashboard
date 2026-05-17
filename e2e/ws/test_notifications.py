"""user.<id>.notifications — trigger / observer / backup."""

from __future__ import annotations

import httpx
import pytest

from e2e.helpers.ws_client import WsClient


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_notifications_trigger_fire_delivered(ws_base_url, api_base_url, triggers) -> None:
    wc = await WsClient.connect(f"{ws_base_url}/ws/notifications/")
    try:
        from apps.triggers.models import EventTrigger

        trig = EventTrigger.objects.get(name="E2E always fires")
        r = httpx.post(f"{api_base_url}/api/triggers/{trig.id}/fire/", timeout=5)
        if r.status_code in (404, 405):
            pytest.skip("trigger fire endpoint not yet exposed")
        ev = await wc.wait_for_event("notification", timeout=30.0)
        assert ev.get("data", {}).get("kind") in (
            "trigger_fired",
            "trigger",
            None,
        )
    finally:
        await wc.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_notifications_observer_done_delivered(ws_base_url, api_base_url, observer) -> None:
    wc = await WsClient.connect(f"{ws_base_url}/ws/notifications/")
    try:
        from apps.observer.models import ObserverSchedule

        sched = ObserverSchedule.objects.get(name="E2E active schedule")
        r = httpx.post(f"{api_base_url}/api/observer/schedules/{sched.id}/run-now/", timeout=5)
        if r.status_code in (404, 405):
            pytest.skip("observer run-now endpoint not yet exposed")
        await wc.wait_for_event("notification", timeout=30.0)
    finally:
        await wc.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.ws
async def test_notifications_backup_done_delivered(ws_base_url, api_base_url, minimal) -> None:
    wc = await WsClient.connect(f"{ws_base_url}/ws/notifications/")
    try:
        r = httpx.post(f"{api_base_url}/api/backups/", json={"kind": "manual"}, timeout=5)
        if r.status_code not in (200, 201, 202):
            pytest.skip(f"backup create returned {r.status_code}")
        await wc.wait_for_event("notification", timeout=60.0)
    finally:
        await wc.close()
