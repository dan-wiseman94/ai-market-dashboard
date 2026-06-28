"""Settings gold paths."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.settings import SettingsPage


@pytest.mark.integration
@pytest.mark.ui
def test_provider_api_key_save_round_trip_masked(page, frontend_base_url, minimal) -> None:
    s = SettingsPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    expect(s.card("claude")).to_be_visible(timeout=10_000)
    s.save_api_key("claude", "sk-ant-e2e-dummy-key")
    s.expect_toast("aved", kind="success")
    # Reload: the key is never echoed back in plaintext (write_only / masked).
    s.go()
    expect(s.api_key_input("claude")).not_to_have_value("sk-ant-e2e-dummy-key")


@pytest.mark.integration
@pytest.mark.ui
def test_daily_and_monthly_cap_edit(page, frontend_base_url, minimal) -> None:
    """Edit the per-provider cost caps and assert they persist.

    Caps live on the ProviderCard (/settings), not /costs — the daily/monthly
    cap fields write ProviderConfig.{daily,monthly}_cost_cap_usd via the card's
    Save (which toasts "Saved"). (Previously this only asserted the fields were
    visible.)
    """
    from decimal import Decimal

    from apps.secrets.models import ProviderConfig

    s = SettingsPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    card = s.card("claude")
    expect(card).to_be_visible(timeout=10_000)

    card.get_by_label("Daily cap (USD)").fill("12.50")
    card.get_by_label("Monthly cap (USD)").fill("321.00")
    s.save_btn("claude").click()
    s.expect_toast("aved", kind="success")  # "Saved" — fires after the PATCH commits

    cfg = ProviderConfig.objects.get(provider="claude")
    assert cfg.daily_cost_cap_usd == Decimal("12.50")
    assert cfg.monthly_cost_cap_usd == Decimal("321.00")
