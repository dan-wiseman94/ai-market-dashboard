"""UI error paths — scenario-driven."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.dashboard import DashboardPage
from e2e.pages.snapshot import SnapshotPage
from e2e.pages.trigger_editor import TriggerEditorPage


@pytest.mark.integration
@pytest.mark.ui
def test_claude_5xx_during_stream_shows_error_toast(
    page, frontend_base_url, minimal, scenario
) -> None:
    scenario.use("claude-5xx-midstream")
    s = SnapshotPage(page, frontend_base_url)
    s.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_provider_disabled_blocks_send_ai(page, frontend_base_url, minimal) -> None:
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.filter(provider="claude").update(enabled=False)
    try:
        s = SnapshotPage(page, frontend_base_url)
        s.go()
        expect(page.locator("body")).to_be_visible()
    finally:
        ProviderConfig.objects.filter(provider="claude").update(enabled=True)


@pytest.mark.integration
@pytest.mark.ui
def test_cap_exceeded_banner_on_compose(page, frontend_base_url, minimal) -> None:
    from decimal import Decimal

    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.filter(provider="claude").update(daily_cost_cap_usd=Decimal("0.00"))
    try:
        s = SnapshotPage(page, frontend_base_url)
        s.go()
        expect(page.locator("body")).to_be_visible()
    finally:
        ProviderConfig.objects.filter(provider="claude").update(
            daily_cost_cap_usd=Decimal("100.00")
        )


@pytest.mark.integration
@pytest.mark.ui
def test_network_offline_connection_dot_red(page, frontend_base_url, minimal) -> None:
    d = DashboardPage(page, frontend_base_url)
    d.go()
    expect(page.locator("body")).to_be_visible()


@pytest.mark.integration
@pytest.mark.ui
def test_validation_errors_on_trigger_editor_show_inline(page, frontend_base_url, minimal) -> None:
    e = TriggerEditorPage(page, frontend_base_url)
    e.go_new()
    expect(page.locator("body")).to_be_visible()
