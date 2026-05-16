"""Visual regression helpers — stability waits + masking + simple baseline diff.

Playwright Python lacks the ``expect(page).to_have_screenshot()`` assertion
that Playwright Test (Node) provides. We roll our own:

* ``wait_for_stable`` kills animations, freezes pointer-driven overlays, waits
  for any skeleton to detach, and waits for fonts.
* ``capture_or_compare`` either creates a baseline on first run (when the file
  is missing) or compares pixel-for-pixel against the committed one. Failures
  write an ``<actual>.png`` next to the baseline for the reviewer.

This is intentionally simpler than Playwright Test's diff: any byte change
between the new screenshot and the baseline fails the test. Use generous
masks on the dynamic regions (timestamps, charts, notification counts) to
avoid churn.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

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


_BASELINE_ROOT = Path("e2e/visual/__screenshots__")


def capture_or_compare(page: Page, name: str, *, mask: list[Locator] | None = None) -> None:
    """Capture ``page`` screenshot to ``e2e/visual/__screenshots__/<name>.png``.

    On first run (no baseline): create the baseline; the test passes.
    On subsequent runs: compare bytes. On mismatch, write
    ``__screenshots__/<name>.actual.png`` next to the baseline and raise
    AssertionError.
    """
    _BASELINE_ROOT.mkdir(parents=True, exist_ok=True)
    baseline = _BASELINE_ROOT / f"{name}.png"
    actual_bytes = page.screenshot(
        full_page=False,
        mask=mask or [],
        type="png",
    )
    if not baseline.exists():
        baseline.write_bytes(actual_bytes)
        return
    if baseline.read_bytes() != actual_bytes:
        diff_path = _BASELINE_ROOT / f"{name}.actual.png"
        diff_path.write_bytes(actual_bytes)
        raise AssertionError(
            f"visual diff for {name}: see {diff_path} (baseline {baseline}). "
            "Inspect, then `make e2e-visual-update` to accept."
        )
