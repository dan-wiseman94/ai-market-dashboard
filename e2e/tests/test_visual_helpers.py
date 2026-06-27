"""Unit tests for visual helpers — API shape + pixel-tolerance diff behavior."""

from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import Image


def test_visual_helper_api() -> None:
    from e2e.helpers import visual

    for attr in (
        "wait_for_stable",
        "default_masks",
        "disable_animations",
        "suppress_pointer_effects",
        "capture_or_compare",
    ):
        assert hasattr(visual, attr), f"missing {attr}"


def _png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (100, 100)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _png_with_changed_pixels(base: bytes, n: int) -> bytes:
    """Return ``base`` with ``n`` pixels flipped to white (a large per-channel delta)."""
    img = Image.open(io.BytesIO(base)).convert("RGB")
    w, _ = img.size
    for i in range(n):
        img.putpixel((i % w, i // w), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _FakePage:
    def __init__(self, png: bytes) -> None:
        self._png = png

    def screenshot(self, **_: Any) -> bytes:
        return self._png


def test_identical_images_pass(tmp_path: Any, monkeypatch: Any) -> None:
    from e2e.helpers import visual

    monkeypatch.setattr(visual, "_BASELINE_ROOT", tmp_path)
    png = _png_bytes((10, 20, 30))
    visual.capture_or_compare(_FakePage(png), "shot")  # first run writes baseline
    visual.capture_or_compare(_FakePage(png), "shot")  # identical → no raise


def test_subpixel_diff_within_tolerance_passes(tmp_path: Any, monkeypatch: Any) -> None:
    """A handful of changed pixels (well under max_diff_ratio) must NOT fail — this
    is the whole point of replacing the byte-exact differ (AA/sub-pixel churn)."""
    from e2e.helpers import visual

    monkeypatch.setattr(visual, "_BASELINE_ROOT", tmp_path)
    base = _png_bytes((10, 20, 30), size=(100, 100))  # 10_000 px
    visual.capture_or_compare(_FakePage(base), "shot")
    # 5 / 10_000 = 0.0005 < default 0.001 ratio.
    visual.capture_or_compare(_FakePage(_png_with_changed_pixels(base, 5)), "shot")


def test_large_diff_fails_and_writes_actual(tmp_path: Any, monkeypatch: Any) -> None:
    from e2e.helpers import visual

    monkeypatch.setattr(visual, "_BASELINE_ROOT", tmp_path)
    base = _png_bytes((10, 20, 30), size=(50, 50))
    visual.capture_or_compare(_FakePage(base), "shot")
    other = _png_bytes((200, 60, 70), size=(50, 50))  # every pixel differs
    with pytest.raises(AssertionError):
        visual.capture_or_compare(_FakePage(other), "shot")
    assert (tmp_path / "shot.actual.png").exists(), "the actual PNG must be written on failure"


def test_dimension_mismatch_fails_cleanly(tmp_path: Any, monkeypatch: Any) -> None:
    """A baseline/actual size mismatch must raise a clear AssertionError, not crash
    inside Pillow (ImageChops on mismatched sizes raises ValueError)."""
    from e2e.helpers import visual

    monkeypatch.setattr(visual, "_BASELINE_ROOT", tmp_path)
    visual.capture_or_compare(_FakePage(_png_bytes((0, 0, 0), (10, 10))), "shot")
    with pytest.raises(AssertionError):
        visual.capture_or_compare(_FakePage(_png_bytes((0, 0, 0), (20, 20))), "shot")
