"""Visual regression helpers — stability waits + masking.

``wait_for_stable`` is the entry point every visual test calls before snapshot
capture; it kills animations, freezes pointer-driven overlays, waits for any
skeleton to detach, and waits for fonts.

``default_masks(page)`` returns the locator set masked on every baseline so we
don't churn diffs on dynamic content (timestamps, notification counts, etc.).
"""

from __future__ import annotations

import contextlib

from playwright.sync_api import Locator, Page


def disable_animations(page: Page) -> None:
    page.add_style_tag(
        content=(
            "*, *::before, *::after { "
            "animation: none !important; "
            "animation-duration: 0s !important; "
            "transition: none !important; "
            "transition-duration: 0s !important; "
            "caret-color: transparent !important; "
            "}"
        )
    )


def suppress_pointer_effects(page: Page) -> None:
    page.add_style_tag(
        content=(
            "canvas, svg, [data-chart] { pointer-events: none !important; } "
            "[data-hover], [data-hover='true'] { opacity: 0 !important; }"
        )
    )


def wait_for_stable(page: Page, timeout_ms: int = 5_000) -> None:
    page.wait_for_load_state("networkidle")
    page.evaluate("() => document.fonts.ready")
    with contextlib.suppress(Exception):
        page.wait_for_selector("[data-testid^='skeleton-']", state="detached", timeout=timeout_ms)
    disable_animations(page)
    suppress_pointer_effects(page)


def default_masks(page: Page) -> list[Locator]:
    """The shared mask set applied on every page-level screenshot."""
    return [
        page.get_by_test_id("cost-tile-today"),
        page.get_by_test_id("notification-bell"),
        page.locator(".timestamp"),
        page.locator("[data-chart] canvas"),
        page.get_by_test_id("breadcrumb-trail"),
    ]
