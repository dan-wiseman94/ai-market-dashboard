"""Unit tests for visual helpers."""

from __future__ import annotations


def test_visual_helper_api() -> None:
    from e2e.helpers import visual

    for attr in (
        "wait_for_stable",
        "default_masks",
        "disable_animations",
        "suppress_pointer_effects",
    ):
        assert hasattr(visual, attr), f"missing {attr}"
