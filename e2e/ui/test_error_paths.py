"""UI error / edge paths — assert the real failure surface, not just a rendered <body>.

The previous version of every test here set up a condition then asserted only
``expect(page.locator("body")).to_be_visible()`` — true for any HTML, including a
crashed page. These drive the real failure and assert what the user actually sees.

Note on surfaces: a stream/provider failure shows up *inline* as a "failed"
assistant message (StreamingMessage's loss-tone pill + error text), not a toast
or a compose banner — the old test names were aspirational. Two states have no
honest UI surface to assert and are skipped with the reason documented below.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.dashboard import DashboardPage
from e2e.pages.thread_detail import ThreadDetailPage
from e2e.pages.trigger_editor import TriggerEditorPage


def _fresh_chat_thread(title: str) -> int:
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    profile = TradingProfile.objects.filter(name="E2E Default").first()
    return Thread.objects.create(title=title, profile=profile, kind="chat").id


@pytest.mark.integration
@pytest.mark.ui
def test_claude_5xx_midstream_shows_failed_message(
    page, frontend_base_url, threads, scenario
) -> None:
    """A mid-stream provider 5xx leaves a visible 'failed' assistant message.

    ``claude-5xx-midstream`` streams partial text then errors; the scenario now
    reaches the worker, so the assistant message flips to failed and the error
    string renders inline (StreamingMessage). No toast — it's inline.
    """
    scenario.use("claude-5xx-midstream")
    tid = _fresh_chat_thread("E2E 5xx midstream")
    detail = ThreadDetailPage(page, frontend_base_url)
    detail.go(tid)
    expect(detail.compose).to_be_visible(timeout=10_000)
    detail.send("please fail mid-stream")

    # The mock error message (apps/core/mocks: stream_then_500) surfaces verbatim.
    # Generous timeout: a warm worker renders in ~1s, but a cold worker or a busy
    # task queue (beat firings in a long-lived e2e DB) can delay the failed write.
    expect(page.get_by_text("provider_500")).to_be_visible(timeout=45_000)


@pytest.mark.integration
@pytest.mark.ui
def test_provider_disabled_blocks_send(page, frontend_base_url, threads) -> None:
    """Disabling the provider gates the run: run_ai_on_message _fails 'provider_disabled'
    (apps/threads/tasks.py gates on ProviderConfig.enabled after resolve).

    We drive the send through the real composer, then assert the gate's deterministic
    effect — a failed assistant message — at the DB layer. The inline UI render of this
    particular failure is racy: a no-stream _fail(event="error") returns in ~20ms, and the
    error WS event can be clobbered by the send mutation's onSuccess refetch (the error
    path doesn't refetch). The cost-cap path (next test) renders reliably.
    """
    import time

    from apps.secrets.models import ProviderConfig
    from apps.threads.models import Message

    ProviderConfig.objects.filter(provider="claude").update(enabled=False)
    try:
        tid = _fresh_chat_thread("E2E provider disabled")
        detail = ThreadDetailPage(page, frontend_base_url)
        detail.go(tid)
        detail.send("should be blocked")
        deadline = time.time() + 20
        failed = None
        while time.time() < deadline:
            failed = Message.objects.filter(
                thread_id=tid, role="assistant", status="failed"
            ).first()
            if failed is not None:
                break
            time.sleep(0.5)
        assert failed is not None, "disabling the provider must gate the run with a failed message"
        assert "disabled" in (failed.error or "").lower(), failed.error
    finally:
        ProviderConfig.objects.filter(provider="claude").update(enabled=True)


@pytest.mark.integration
@pytest.mark.ui
def test_cap_exceeded_shows_failed_message(page, frontend_base_url, threads) -> None:
    """A tripped cost cap _fails with event=cost_capped; the frontend onWs seeds a
    complete failed message (id/role) so the bubble renders cleanly (no React key warning)."""
    from decimal import Decimal

    from apps.secrets.models import ProviderConfig

    # Negative cap so `spent + 0 > cap` trips deterministically (cap=0 only trips with prior spend).
    ProviderConfig.objects.filter(provider="claude").update(daily_cost_cap_usd=Decimal("-1"))
    try:
        tid = _fresh_chat_thread("E2E cap exceeded")
        detail = ThreadDetailPage(page, frontend_base_url)
        detail.go(tid)
        detail.send("should hit the cap")
        expect(page.get_by_text("would be exceeded")).to_be_visible(timeout=20_000)
    finally:
        ProviderConfig.objects.filter(provider="claude").update(
            daily_cost_cap_usd=Decimal("100.00")
        )


@pytest.mark.integration
@pytest.mark.ui
def test_health_failure_turns_connection_dot_offline(page, frontend_base_url, minimal) -> None:
    """When the health poll fails, the connection dot latches 'Offline'.

    We fail the poll by aborting /api/health rather than going browser-offline:
    react-query's default ``networkMode: 'online'`` *pauses* queries when the
    browser is offline (so they never error and the dot stays Live). Aborting
    while online makes the query actually fail → useHealth returns "down".
    """
    d = DashboardPage(page, frontend_base_url)
    d.go()
    dot = page.get_by_test_id("connection-status-dot")
    # Healthy on arrival …
    expect(dot).to_have_attribute("aria-label", "Connection: Live", timeout=15_000)
    # … then every health poll fails (browser stays online; abort → ERR_FAILED).
    page.route("**/api/health/**", lambda route: route.abort())
    expect(dot).to_have_attribute("aria-label", "Connection: Offline", timeout=20_000)


@pytest.mark.integration
@pytest.mark.ui
def test_trigger_editor_blocks_save_until_named(page, frontend_base_url, minimal) -> None:
    """The trigger editor's Save is disabled while the form is invalid (empty name).

    That disabled state is the editor's validation gate (TriggerEditorPage:
    ``disabled={... || !form.name || !profileId}``) — submitting an invalid
    trigger is simply not possible, which is what we assert.
    """
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    save_btn = page.get_by_role("button", name="Save")
    expect(save_btn).to_be_visible(timeout=10_000)
    expect(save_btn).to_be_disabled()
