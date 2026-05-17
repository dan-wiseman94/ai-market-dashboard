"""Enforces ≤500KB per visual baseline."""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 500 * 1024


def test_no_baseline_exceeds_500kb() -> None:
    root = Path("e2e/visual/__screenshots__")
    if not root.exists():
        return
    oversize = [p for p in root.rglob("*.png") if p.stat().st_size > MAX_BYTES]
    assert not oversize, f"baselines exceeding 500KB: {[str(p) for p in oversize]}"
