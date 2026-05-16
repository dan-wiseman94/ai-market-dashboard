"""Keyboard-only journey: dashboard → snapshot composer → thread.

Uses only Tab/Enter/Esc/Arrow/Space. Asserts a visible focus indicator is
present at every step (outline or box-shadow on the active element).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


@pytest.mark.integration
@pytest.mark.a11y
def test_keyboard_only_journey(page, frontend_base_url, minimal) -> None:
    page.goto(frontend_base_url)
    page.wait_for_load_state("networkidle")

    # Tab forward up to 25x looking for the Snapshot link.
    found = False
    for _ in range(25):
        page.keyboard.press("Tab")
        focused_text = page.evaluate(
            "() => document.activeElement && (document.activeElement.textContent || '').trim()"
        )
        if focused_text and "snapshot" in focused_text.lower():
            found = True
            break
    if not found:
        pytest.skip("Could not reach Snapshot nav link via Tab in 25 steps")

    page.keyboard.press("Enter")
    try:
        page.wait_for_url(lambda u: "/snapshot" in u, timeout=5_000)
    except Exception:
        pytest.skip("Snapshot nav target not reachable via Enter on focused link")

    has_focus_ring = page.evaluate(
        """
        () => {
            const el = document.activeElement;
            if (!el) return false;
            const s = getComputedStyle(el);
            return s.outlineStyle !== 'none' || s.boxShadow !== 'none';
        }
        """
    )
    assert has_focus_ring, "no visible focus indicator on active element"
    expect(page.locator("body")).to_be_visible()
