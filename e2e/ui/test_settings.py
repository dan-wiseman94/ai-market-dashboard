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
    s = SettingsPage(page, frontend_base_url)
    s.go()
    s.expect_error_boundary_absent()
    # The ProviderCard on /settings has Daily cap and Monthly cap fields.
    expect(s.card("claude")).to_be_visible(timeout=10_000)
    card = s.card("claude")
    expect(card.get_by_label("Daily cap (USD)")).to_be_visible(timeout=10_000)
    expect(card.get_by_label("Monthly cap (USD)")).to_be_visible()
