"""Keyboard-only journey: dashboard → snapshot composer.

Uses only Tab/Enter. Reaching the Snapshot nav link via Tab and activating it
are REQUIREMENTS for a keyboard user, so a miss is a hard failure — not a skip.
(Previously both failure paths called ``pytest.skip``, so a broken keyboard
path silently skipped instead of failing.)
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

_FOCUS_RING_JS = """
() => {
    const el = document.activeElement;
    if (!el) return { ok: false, reason: 'no active element' };
    const s = getComputedStyle(el);
    const outlineW = parseFloat(s.outlineWidth) || 0;
    const hasOutline = s.outlineStyle !== 'none' && outlineW > 0;
    const hasShadow = !!s.boxShadow && s.boxShadow !== 'none';
    return {
        ok: hasOutline || hasShadow,
        outlineStyle: s.outlineStyle,
        outlineWidth: s.outlineWidth,
        boxShadow: s.boxShadow,
        tag: el.tagName,
    };
}
"""


@pytest.mark.integration
@pytest.mark.a11y
def test_keyboard_only_journey(page, frontend_base_url, minimal) -> None:
    page.goto(frontend_base_url)
    page.wait_for_load_state("networkidle")

    # Tab forward up to 25x looking for the Snapshot nav link. Reaching it is a
    # requirement, so a miss is a hard failure (not a skip that hides regressions).
    found = False
    for _ in range(25):
        page.keyboard.press("Tab")
        focused_text = page.evaluate(
            "() => document.activeElement && (document.activeElement.textContent || '').trim()"
        )
        if focused_text and "snapshot" in focused_text.lower():
            found = True
            break
    assert found, "Snapshot nav link not reachable via Tab within 25 steps (keyboard-nav regression)"

    # A keyboard user must SEE where focus is: the focused link needs a visible
    # focus indicator (outline with width, or a box-shadow ring). Asserted on the
    # link itself, before activation — a bare UA default with outline-width 0 fails.
    ring = page.evaluate(_FOCUS_RING_JS)
    assert ring["ok"], f"no visible focus indicator on the focused nav link: {ring}"

    page.keyboard.press("Enter")
    # Raising on timeout IS the assertion — the link must navigate.
    page.wait_for_url(lambda u: "/snapshot" in u, timeout=5_000)
    expect(page.locator("body")).to_be_visible()
