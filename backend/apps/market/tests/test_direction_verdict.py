"""Shared directional-call scorer — used by both thesis post-mortems and
AI predictions, so both judge a directional call identically."""

from __future__ import annotations

import pytest

from apps.market.returns import direction_verdict


@pytest.mark.parametrize(
    ("direction", "fwd", "expected"),
    [
        # None forward return -> inconclusive, regardless of direction
        ("bullish", None, "inconclusive"),
        ("bearish", None, "inconclusive"),
        ("neutral", None, "inconclusive"),
        # bullish
        ("bullish", 5.0, "correct"),
        ("bullish", 1.0, "correct"),  # exactly at the deadzone edge counts
        ("bullish", 0.5, "mixed"),  # inside the deadzone
        ("bullish", -0.5, "mixed"),
        ("bullish", -1.0, "incorrect"),
        ("bullish", -5.0, "incorrect"),
        # bearish (mirror image)
        ("bearish", -5.0, "correct"),
        ("bearish", -1.0, "correct"),
        ("bearish", -0.5, "mixed"),
        ("bearish", 0.5, "mixed"),
        ("bearish", 1.0, "incorrect"),
        ("bearish", 5.0, "incorrect"),
        # neutral: correct iff the move stayed inside the deadzone
        ("neutral", 0.5, "correct"),
        ("neutral", -0.9, "correct"),
        ("neutral", 1.0, "correct"),  # edge inclusive
        ("neutral", 1.5, "incorrect"),
        ("neutral", -2.0, "incorrect"),
    ],
)
def test_direction_verdict_truth_table(direction, fwd, expected):
    assert direction_verdict(direction, fwd) == expected


def test_custom_deadzone_widens_the_mixed_band():
    # With a 3% deadzone, a +2% move is not a bullish "correct".
    assert direction_verdict("bullish", 2.0, deadzone=3.0) == "mixed"
    assert direction_verdict("bullish", 2.0, deadzone=1.0) == "correct"
