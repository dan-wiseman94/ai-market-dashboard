"""Visual regression helpers — stability waits + masking + simple baseline diff.

Playwright Python lacks the ``expect(page).to_have_screenshot()`` assertion
that Playwright Test (Node) provides. We roll our own:

* ``wait_for_stable`` kills animations, freezes pointer-driven overlays, waits
  for any skeleton to detach, and waits for fonts.
* ``capture_or_compare`` either creates a baseline on first run (when the file
  is missing) or compares pixel-for-pixel against the committed one. Failures
  write an ``<actual>.png`` next to the baseline for the reviewer.

Unlike a byte-exact compare, the diff decodes both PNGs and fails only when
the *fraction of pixels that differ by more than a small per-channel delta*
exceeds ``max_diff_ratio``. That tolerance absorbs anti-aliasing/sub-pixel
jitter (which a byte compare flags as a failure) while still catching real
visual regressions. Use masks on genuinely dynamic regions (timestamps,
charts, notification counts) so they never enter the comparison at all.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import Locator, Page

from e2e.helpers.waits import wait_for_app_ready


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


def wait_for_stable(page: Page, timeout_ms: int = 10_000) -> None:
    wait_for_app_ready(page, timeout_ms=timeout_ms)
    page.evaluate("() => document.fonts.ready")
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
        # Cost tables on /costs render seeded random AIRun amounts; mask any
        # element containing a dollar sign to keep the baseline stable.
        page.locator("table:has-text('$')"),
        page.locator("[data-cost-row]"),
        # Relative timestamps ("3 minutes ago") are inherently non-deterministic;
        # the <RelativeTime> component tags them so they're masked out of the diff.
        page.get_by_test_id("relative-time"),
    ]


_BASELINE_ROOT = Path("e2e/visual/__screenshots__")

# A per-channel absolute delta at or below this is treated as "same pixel" —
# absorbs font anti-aliasing and sub-pixel rendering jitter that a byte-exact
# compare would flag. Real regressions move pixels far past this.
_PER_CHANNEL_THRESHOLD = 16


def _fraction_differing(
    baseline: Image.Image, actual: Image.Image, channel_threshold: int
) -> float:
    """Fraction of pixels whose max per-channel |delta| exceeds ``channel_threshold``.

    Both images must already be the same size and mode ``RGB``.
    """
    diff = ImageChops.difference(baseline, actual)
    bands = diff.split()
    max_band = bands[0]
    for band in bands[1:]:
        max_band = ImageChops.lighter(max_band, band)  # per-pixel max across channels
    over = max_band.point(lambda p, t=channel_threshold: 255 if p > t else 0)
    differing = over.histogram()[255]
    total = baseline.width * baseline.height
    return differing / total if total else 0.0


def capture_or_compare(
    page: Page,
    name: str,
    *,
    mask: list[Locator] | None = None,
    max_diff_ratio: float = 0.001,
) -> None:
    """Capture ``page`` screenshot to ``e2e/visual/__screenshots__/<name>.png``.

    On first run (no baseline): create the baseline; the test passes.
    On subsequent runs: decode both PNGs and compare. The test fails only when
    the fraction of pixels differing by more than ``_PER_CHANNEL_THRESHOLD`` per
    channel exceeds ``max_diff_ratio`` (default 0.1%), or when the dimensions
    differ. On failure, write ``__screenshots__/<name>.actual.png`` next to the
    baseline and raise AssertionError.
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

    baseline_img = Image.open(io.BytesIO(baseline.read_bytes())).convert("RGB")
    actual_img = Image.open(io.BytesIO(actual_bytes)).convert("RGB")
    diff_path = _BASELINE_ROOT / f"{name}.actual.png"

    if baseline_img.size != actual_img.size:
        diff_path.write_bytes(actual_bytes)
        raise AssertionError(
            f"visual size mismatch for {name}: baseline {baseline_img.size} vs "
            f"actual {actual_img.size}; see {diff_path}. "
            "Inspect, then `make e2e-visual-update` to accept."
        )

    ratio = _fraction_differing(baseline_img, actual_img, _PER_CHANNEL_THRESHOLD)
    if ratio > max_diff_ratio:
        diff_path.write_bytes(actual_bytes)
        raise AssertionError(
            f"visual diff for {name}: {ratio:.4%} of pixels differ "
            f"(> {max_diff_ratio:.4%} tolerance); see {diff_path} (baseline {baseline}). "
            "Inspect, then `make e2e-visual-update` to accept."
        )
